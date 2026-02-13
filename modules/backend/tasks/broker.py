"""
Taskiq Broker Configuration.

Configures the message broker for background task processing.
Uses Redis as the backend for task queue management.

Usage:
    # Start worker process
    python example.py --action worker

    # Or directly with taskiq
    taskiq worker modules.backend.tasks.broker:broker
"""

import os
from typing import TYPE_CHECKING

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

# Type hints for IDE support
if TYPE_CHECKING:
    from taskiq_redis import ListQueueBroker


def get_redis_url() -> str:
    """
    Get Redis URL from environment.

    Returns:
        Redis connection URL

    Raises:
        RuntimeError: If REDIS_URL is not configured
    """
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        # Try loading from .env file
        try:
            from modules.backend.core.config import get_settings
            settings = get_settings()
            redis_url = settings.redis_url
        except Exception:
            pass

    if not redis_url:
        raise RuntimeError(
            "REDIS_URL not configured. Set REDIS_URL environment variable "
            "or configure it in config/.env"
        )

    return redis_url


def create_broker() -> "ListQueueBroker":
    """
    Create and configure the Taskiq broker.

    Returns:
        Configured ListQueueBroker instance
    """
    from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

    redis_url = get_redis_url()

    # Create result backend for storing task results
    # Results expire after 1 hour by default
    result_backend = RedisAsyncResultBackend(
        redis_url=redis_url,
        result_ex_time=3600,  # 1 hour expiration
    )

    # Create broker with Redis backend
    broker = ListQueueBroker(
        url=redis_url,
        queue_name="bff_tasks",  # Queue name in Redis
    ).with_result_backend(result_backend)

    logger.debug(
        "Taskiq broker configured",
        extra={"queue_name": "bff_tasks", "result_expiry": 3600},
    )

    return broker


# Lazy broker initialization
_broker: "ListQueueBroker | None" = None


def get_broker() -> "ListQueueBroker":
    """
    Get the broker instance, creating it if necessary.

    Returns:
        Configured broker instance
    """
    global _broker
    if _broker is None:
        _broker = create_broker()

        # Register startup and shutdown hooks
        @_broker.on_event("startup")
        async def on_startup() -> None:
            """Initialize resources when worker starts."""
            logger.info("Taskiq worker starting up")

        @_broker.on_event("shutdown")
        async def on_shutdown() -> None:
            """Cleanup resources when worker shuts down."""
            logger.info("Taskiq worker shutting down")

    return _broker


# For direct access (e.g., taskiq worker command)
# This uses __getattr__ for lazy initialization
def __getattr__(name: str):
    """Lazy attribute access for broker."""
    if name == "broker":
        return get_broker()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
