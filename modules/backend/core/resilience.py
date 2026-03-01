"""
Resilience Infrastructure.

Circuit breaker listener, retry callback, and composed resilience patterns.
These are the building blocks referenced by doc 08 (observability) and
doc 16 (concurrency/resilience) for structured resilience event logging.

The composed resilience stack is always applied in this order (outside-in):
    Circuit Breaker (aiobreaker) → Retry (tenacity) → Semaphore → Timeout → Call

Usage:
    from modules.backend.core.resilience import ResilienceLogger, log_retry

    breaker = aiobreaker.CircuitBreaker(
        fail_max=5,
        timeout_duration=30,
        listeners=[ResilienceLogger("database")],
    )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=log_retry,
        reraise=True,
    )
    async def call_external():
        async with get_semaphore("external_api"):
            async with asyncio.timeout(7):
                return await client.get(url)
"""

from typing import Any

import aiobreaker

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class ResilienceLogger(aiobreaker.CircuitBreakerListener):
    """Circuit breaker listener that emits structured resilience events.

    Every state transition is logged with a standardized set of fields
    so that resilience events can be filtered and aggregated:

        jq 'select(.resilience_event != null)' logs/system.jsonl
    """

    def __init__(self, dependency: str) -> None:
        self.dependency = dependency

    def state_change(self, cb: aiobreaker.CircuitBreaker, old_state: Any, new_state: Any) -> None:
        event_map = {
            "open": "circuit_breaker_opened",
            "half-open": "circuit_breaker_half_open",
            "closed": "circuit_breaker_closed",
        }
        new_str = str(new_state).lower()
        event = event_map.get(new_str, f"circuit_breaker_{new_str}")
        log_level = "error" if new_str == "open" else "info"

        getattr(logger, log_level)(
            f"Circuit breaker {self.dependency}: {old_state} → {new_state}",
            extra={
                "resilience_event": event,
                "dependency": self.dependency,
                "failure_count": cb.fail_counter,
            },
        )

    def failure(self, cb: aiobreaker.CircuitBreaker, exception: Exception) -> None:
        logger.warning(
            f"Circuit breaker {self.dependency}: failure recorded",
            extra={
                "resilience_event": "circuit_breaker_failure",
                "dependency": self.dependency,
                "failure_count": cb.fail_counter,
                "error": str(exception),
            },
        )


def log_retry(retry_state: Any) -> None:
    """Tenacity before_sleep callback that emits structured retry events.

    Pass this as `before_sleep=log_retry` in any @retry decorator.

    Args:
        retry_state: tenacity.RetryCallState instance
    """
    duration_ms = None
    if retry_state.outcome_timestamp and retry_state.start_time:
        duration_ms = round(
            (retry_state.outcome_timestamp - retry_state.start_time) * 1000
        )

    error = None
    if retry_state.outcome and retry_state.outcome.failed:
        error = str(retry_state.outcome.exception())

    fn_name = getattr(retry_state.fn, "__name__", "unknown")

    logger.warning(
        f"Retrying {fn_name} (attempt {retry_state.attempt_number})",
        extra={
            "resilience_event": "retry_attempt",
            "dependency": fn_name,
            "attempt": retry_state.attempt_number,
            "duration_ms": duration_ms,
            "error": error,
        },
    )


def create_circuit_breaker(
    dependency: str,
    fail_max: int = 5,
    timeout_duration: int = 30,
) -> aiobreaker.CircuitBreaker:
    """Create a circuit breaker with structured logging.

    Args:
        dependency: Name of the external dependency (for logging)
        fail_max: Number of failures before opening
        timeout_duration: Seconds to wait before half-open test

    Returns:
        Configured CircuitBreaker instance
    """
    return aiobreaker.CircuitBreaker(
        fail_max=fail_max,
        timeout_duration=timeout_duration,
        listeners=[ResilienceLogger(dependency)],
    )
