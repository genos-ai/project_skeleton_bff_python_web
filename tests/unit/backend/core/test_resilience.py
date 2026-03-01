"""Unit tests for modules.backend.core.resilience."""

from unittest.mock import MagicMock, patch

import pytest

from modules.backend.core.resilience import (
    ResilienceLogger,
    create_circuit_breaker,
    log_retry,
)


class TestResilienceLogger:
    def test_state_change_open(self):
        """Opening the circuit should log at error level."""
        rl = ResilienceLogger("db")
        mock_cb = MagicMock()
        mock_cb.fail_counter = 5

        with patch("modules.backend.core.resilience.logger") as mock_logger:
            rl.state_change(mock_cb, "closed", "open")
            mock_logger.error.assert_called_once()
            call_kwargs = mock_logger.error.call_args
            assert "circuit_breaker_opened" in str(call_kwargs)

    def test_state_change_closed(self):
        """Closing the circuit should log at info level."""
        rl = ResilienceLogger("db")
        mock_cb = MagicMock()
        mock_cb.fail_counter = 0

        with patch("modules.backend.core.resilience.logger") as mock_logger:
            rl.state_change(mock_cb, "open", "closed")
            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args
            assert "circuit_breaker_closed" in str(call_kwargs)

    def test_state_change_half_open(self):
        """Half-open should log at info level."""
        rl = ResilienceLogger("redis")
        mock_cb = MagicMock()
        mock_cb.fail_counter = 3

        with patch("modules.backend.core.resilience.logger") as mock_logger:
            rl.state_change(mock_cb, "open", "half-open")
            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args
            assert "circuit_breaker_half_open" in str(call_kwargs)

    def test_failure(self):
        """Recording a failure should log at warning level."""
        rl = ResilienceLogger("external")
        mock_cb = MagicMock()
        mock_cb.fail_counter = 2

        with patch("modules.backend.core.resilience.logger") as mock_logger:
            rl.failure(mock_cb, ConnectionError("timeout"))
            mock_logger.warning.assert_called_once()
            call_kwargs = mock_logger.warning.call_args
            assert "circuit_breaker_failure" in str(call_kwargs)


class TestLogRetry:
    def test_emits_structured_event(self):
        """log_retry should emit a warning with retry metadata."""
        mock_state = MagicMock()
        mock_state.attempt_number = 2
        mock_state.fn.__name__ = "call_api"
        mock_state.outcome_timestamp = 1000.5
        mock_state.start_time = 1000.0
        mock_state.outcome.failed = True
        mock_state.outcome.exception.return_value = ConnectionError("fail")

        with patch("modules.backend.core.resilience.logger") as mock_logger:
            log_retry(mock_state)
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "call_api" in call_args[0][0]
            assert call_args[1]["extra"]["resilience_event"] == "retry_attempt"
            assert call_args[1]["extra"]["attempt"] == 2

    def test_handles_no_outcome(self):
        """log_retry should not crash if outcome is None."""
        mock_state = MagicMock()
        mock_state.attempt_number = 1
        mock_state.fn.__name__ = "fetch"
        mock_state.outcome_timestamp = None
        mock_state.start_time = None
        mock_state.outcome = None

        with patch("modules.backend.core.resilience.logger") as mock_logger:
            log_retry(mock_state)
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert call_args[1]["extra"]["duration_ms"] is None
            assert call_args[1]["extra"]["error"] is None


class TestCreateCircuitBreaker:
    def test_returns_configured_breaker(self):
        """create_circuit_breaker should return a breaker with correct config."""
        cb = create_circuit_breaker("redis", fail_max=3, timeout_duration=15)
        assert cb.fail_max == 3
        assert cb.timeout_duration == 15
        assert len(cb.listeners) == 1
        assert isinstance(cb.listeners[0], ResilienceLogger)
        assert cb.listeners[0].dependency == "redis"

    def test_default_values(self):
        """Default values should be fail_max=5, timeout_duration=30."""
        cb = create_circuit_breaker("default-dep")
        assert cb.fail_max == 5
        assert cb.timeout_duration == 30
