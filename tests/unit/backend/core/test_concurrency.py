"""Unit tests for modules.backend.core.concurrency."""

import asyncio
import contextvars
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog

from modules.backend.core.concurrency import (
    TracedThreadPoolExecutor,
    _semaphore_capacities,
    _semaphores,
    get_cpu_pool,
    get_io_pool,
    get_interpreter_pool,
    get_semaphore,
    shutdown_pools,
)
import modules.backend.core.concurrency as concurrency_module


@pytest.fixture(autouse=True)
def _reset_pools():
    """Reset global pool state before and after each test."""
    concurrency_module._io_pool = None
    concurrency_module._cpu_pool = None
    if hasattr(concurrency_module, "_interp_pool"):
        concurrency_module._interp_pool = None
    concurrency_module._semaphores.clear()
    concurrency_module._semaphore_capacities.clear()
    yield
    # Cleanup after test
    if concurrency_module._io_pool is not None:
        concurrency_module._io_pool.shutdown(wait=False)
        concurrency_module._io_pool = None
    if concurrency_module._cpu_pool is not None:
        concurrency_module._cpu_pool.shutdown(wait=False)
        concurrency_module._cpu_pool = None
    if getattr(concurrency_module, "_interp_pool", None) is not None:
        concurrency_module._interp_pool.shutdown(wait=False)
        concurrency_module._interp_pool = None
    concurrency_module._semaphores.clear()
    concurrency_module._semaphore_capacities.clear()


def _mock_concurrency_config(thread_max=4, process_max=2, sem_database=50):
    """Create a mock concurrency config."""
    mock_config = MagicMock()
    mock_config.concurrency.thread_pool.max_workers = thread_max
    mock_config.concurrency.process_pool.max_workers = process_max
    mock_config.concurrency.semaphores.database = sem_database
    mock_config.concurrency.semaphores.redis = 100
    mock_config.concurrency.semaphores.external_api = 20
    mock_config.concurrency.semaphores.llm = 5
    return mock_config


class TestTracedThreadPoolExecutor:
    def test_propagates_contextvars(self):
        """Contextvars set in the caller should be visible in the worker thread."""
        test_var = contextvars.ContextVar("test_var", default="default")
        test_var.set("from_caller")

        executor = TracedThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(test_var.get)
            result = future.result(timeout=5)
            assert result == "from_caller"
        finally:
            executor.shutdown(wait=True)

    def test_propagates_structlog_context(self):
        """Structlog contextvars should be available in worker threads."""
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id="test-123")

        executor = TracedThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(structlog.contextvars.get_contextvars)
            result = future.result(timeout=5)
            assert result.get("request_id") == "test-123"
        finally:
            executor.shutdown(wait=True)
            structlog.contextvars.clear_contextvars()

    def test_executes_function(self):
        """Basic function execution should work."""
        executor = TracedThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(lambda x, y: x + y, 3, 4)
            assert future.result(timeout=5) == 7
        finally:
            executor.shutdown(wait=True)


class TestGetIoPool:
    @patch("modules.backend.core.config.get_app_config")
    def test_creates_pool_lazily(self, mock_get_config):
        mock_get_config.return_value = _mock_concurrency_config(thread_max=4)

        pool1 = get_io_pool()
        pool2 = get_io_pool()
        assert pool1 is pool2
        assert isinstance(pool1, TracedThreadPoolExecutor)
        assert pool1._max_workers == 4

    @patch("modules.backend.core.config.get_app_config")
    def test_uses_config_max_workers(self, mock_get_config):
        mock_get_config.return_value = _mock_concurrency_config(thread_max=8)

        pool = get_io_pool()
        assert pool._max_workers == 8


class TestGetCpuPool:
    @patch("modules.backend.core.config.get_app_config")
    def test_creates_pool_lazily(self, mock_get_config):
        mock_get_config.return_value = _mock_concurrency_config(process_max=2)

        pool1 = get_cpu_pool()
        pool2 = get_cpu_pool()
        assert pool1 is pool2
        assert pool1._max_workers == 2


class TestGetInterpreterPool:
    """InterpreterPoolExecutor is available only on Python 3.14+."""

    def test_returns_none_or_executor(self):
        """get_interpreter_pool() returns None on <3.14 or an executor on 3.14+."""
        result = get_interpreter_pool()
        if sys.version_info >= (3, 14):
            assert result is not None
            assert hasattr(result, "submit") and hasattr(result, "shutdown")
        else:
            assert result is None

    @pytest.mark.skipif(sys.version_info < (3, 14), reason="InterpreterPoolExecutor requires Python 3.14+")
    @patch("modules.backend.core.config.get_app_config")
    def test_creates_pool_lazily_on_314(self, mock_get_config):
        mock_get_config.return_value = _mock_concurrency_config(process_max=2)

        pool1 = get_interpreter_pool()
        pool2 = get_interpreter_pool()
        assert pool1 is pool2
        assert pool1 is not None
        assert pool1._max_workers == 2


class TestGetSemaphore:
    @patch("modules.backend.core.config.get_app_config")
    def test_creates_with_config_capacity(self, mock_get_config):
        mock_get_config.return_value = _mock_concurrency_config(sem_database=50)

        sem = get_semaphore("database")
        assert sem._value == 50
        assert _semaphore_capacities["database"] == 50

    @patch("modules.backend.core.config.get_app_config")
    def test_returns_same_instance(self, mock_get_config):
        mock_get_config.return_value = _mock_concurrency_config()

        sem1 = get_semaphore("database")
        sem2 = get_semaphore("database")
        assert sem1 is sem2

    @patch("modules.backend.core.config.get_app_config")
    def test_defaults_to_20_for_unknown(self, mock_get_config):
        mock_config = _mock_concurrency_config()
        del mock_config.concurrency.semaphores.unknown_dep
        mock_get_config.return_value = mock_config

        sem = get_semaphore("unknown_dep")
        assert sem._value == 20


class TestShutdownPools:
    @patch("modules.backend.core.config.get_app_config")
    @pytest.mark.asyncio
    async def test_cleans_up(self, mock_get_config):
        mock_get_config.return_value = _mock_concurrency_config()

        # Create pools and semaphore
        get_io_pool()
        get_semaphore("database")

        assert concurrency_module._io_pool is not None
        assert len(concurrency_module._semaphores) == 1

        await shutdown_pools()

        assert concurrency_module._io_pool is None
        assert concurrency_module._cpu_pool is None
        assert len(concurrency_module._semaphores) == 0
        assert len(concurrency_module._semaphore_capacities) == 0
