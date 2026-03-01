"""
Concurrency Infrastructure.

Thread pool, process pool, and semaphore management for the application.
All pools are created lazily on first access and cleaned up during shutdown.

Pools:
    _io_pool    - TracedThreadPoolExecutor for blocking I/O (asyncio.to_thread replacement)
    _cpu_pool   - ProcessPoolExecutor for CPU-bound work
    _interp_pool - InterpreterPoolExecutor (Python 3.14+ only) for sub-interpreter parallelism

Semaphores:
    Created per-dependency to limit concurrent access to external services.
    Sizing is configured in config/settings/concurrency.yaml.

Python 3.14+ only:
    - get_interpreter_pool() returns an InterpreterPoolExecutor (sub-interpreters, independent GILs).
    - For debugging stuck async: python -m asyncio pstree <PID>

Usage:
    from modules.backend.core.concurrency import get_io_pool, get_cpu_pool, get_semaphore

    # Run blocking code in thread pool (preserves structlog context)
    result = await loop.run_in_executor(get_io_pool(), blocking_fn, arg)

    # Run CPU-bound code in process pool
    result = await loop.run_in_executor(get_cpu_pool(), cpu_fn, arg)

    # On Python 3.14+: optional interpreter pool (lower startup than process pool)
    interp = get_interpreter_pool()
    if interp is not None:
        result = await loop.run_in_executor(interp, cpu_fn, arg)
    else:
        result = await loop.run_in_executor(get_cpu_pool(), cpu_fn, arg)

    # Limit concurrent access to external API
    async with get_semaphore("external_api"):
        result = await client.get(url)
"""

import asyncio
import contextvars
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

_io_pool: ThreadPoolExecutor | None = None
_cpu_pool: ProcessPoolExecutor | None = None
_semaphores: dict[str, asyncio.Semaphore] = {}
_semaphore_capacities: dict[str, int] = {}

if sys.version_info >= (3, 14):
    from concurrent.futures import InterpreterPoolExecutor
    _interp_pool: InterpreterPoolExecutor | None = None
else:
    InterpreterPoolExecutor = None  # type: ignore[misc, assignment]
    _interp_pool: Any = None


class TracedThreadPoolExecutor(ThreadPoolExecutor):
    """ThreadPoolExecutor that propagates contextvars to worker threads.

    Standard ThreadPoolExecutor does not carry structlog context, request_id,
    or OpenTelemetry spans into worker threads. This subclass copies the
    current context before dispatching, so all observability data is preserved.
    """

    def submit(self, fn, /, *args, **kwargs):
        ctx = contextvars.copy_context()
        return super().submit(ctx.run, fn, *args, **kwargs)


def get_io_pool() -> TracedThreadPoolExecutor:
    """Get the shared thread pool for blocking I/O operations.

    Creates the pool lazily on first call using config from concurrency.yaml.
    """
    global _io_pool
    if _io_pool is None:
        from modules.backend.core.config import get_app_config
        max_workers = get_app_config().concurrency.thread_pool.max_workers
        _io_pool = TracedThreadPoolExecutor(max_workers=max_workers)
        logger.info("Thread pool created", extra={"max_workers": max_workers})
    return _io_pool


def get_cpu_pool() -> ProcessPoolExecutor:
    """Get the shared process pool for CPU-bound operations.

    Creates the pool lazily on first call using config from concurrency.yaml.
    """
    global _cpu_pool
    if _cpu_pool is None:
        from modules.backend.core.config import get_app_config
        max_workers = get_app_config().concurrency.process_pool.max_workers
        _cpu_pool = ProcessPoolExecutor(max_workers=max_workers)
        logger.info("Process pool created", extra={"max_workers": max_workers})
    return _cpu_pool


def get_interpreter_pool() -> Any:
    """Get the shared interpreter pool (Python 3.14+ only).

    Sub-interpreters with independent GILs; lower startup cost than process pool.
    Returns None on Python < 3.14. Use for short-lived CPU-bound tasks where
    process startup overhead matters (see doc 16).
    """
    global _interp_pool
    if InterpreterPoolExecutor is None:
        return None
    if _interp_pool is None:
        from modules.backend.core.config import get_app_config
        max_workers = get_app_config().concurrency.process_pool.max_workers
        _interp_pool = InterpreterPoolExecutor(max_workers=max_workers)
        logger.info(
            "Interpreter pool created (3.14+)",
            extra={"max_workers": max_workers},
        )
    return _interp_pool


def get_semaphore(name: str) -> asyncio.Semaphore:
    """Get a named semaphore for concurrency-limiting external calls.

    Semaphores are created lazily. The capacity is read from concurrency.yaml
    under `semaphores.<name>`. If the name is not configured, defaults to 20.
    """
    if name not in _semaphores:
        from modules.backend.core.config import get_app_config
        semaphore_config = get_app_config().concurrency.semaphores
        capacity = getattr(semaphore_config, name, 20)
        _semaphores[name] = asyncio.Semaphore(capacity)
        _semaphore_capacities[name] = capacity
        logger.debug("Semaphore created", extra={"name": name, "capacity": capacity})
    return _semaphores[name]


async def shutdown_pools() -> None:
    """Shut down all pools gracefully. Called during application shutdown.

    Pool shutdown is blocking, so we run it in a thread to avoid stalling
    the event loop during graceful shutdown.
    """
    global _io_pool, _cpu_pool, _interp_pool

    if _io_pool is not None:
        await asyncio.to_thread(_io_pool.shutdown, wait=True)
        logger.info("Thread pool shut down")
        _io_pool = None

    if _cpu_pool is not None:
        await asyncio.to_thread(_cpu_pool.shutdown, wait=True)
        logger.info("Process pool shut down")
        _cpu_pool = None

    if _interp_pool is not None:
        await asyncio.to_thread(_interp_pool.shutdown, wait=True)
        logger.info("Interpreter pool shut down")
        _interp_pool = None

    _semaphores.clear()
    _semaphore_capacities.clear()
    logger.debug("Semaphores cleared")
