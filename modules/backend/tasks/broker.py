"""
Taskiq Broker Configuration.

Configures the message broker for background task processing.
Uses Redis as the backend for task queue management.

Usage:
    # Start worker process
    python cli.py --service worker

    # Or directly with taskiq
    taskiq worker modules.backend.tasks.broker:broker
"""

from typing import TYPE_CHECKING

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from taskiq_redis import ListQueueBroker


def create_broker() -> "ListQueueBroker":
    """
    Create and configure the Taskiq broker.

    Configuration loaded from config/settings/database.yaml (redis.broker section).

    Returns:
        Configured ListQueueBroker instance
    """
    from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

    from modules.backend.core.config import get_app_config, get_redis_url

    redis_url = get_redis_url()
    broker_config = get_app_config().database["redis"]["broker"]
    queue_name = broker_config["queue_name"]
    result_expiry = broker_config["result_expiry_seconds"]

    result_backend = RedisAsyncResultBackend(
        redis_url=redis_url,
        result_ex_time=result_expiry,
    )

    broker = ListQueueBroker(
        url=redis_url,
        queue_name=queue_name,
    ).with_result_backend(result_backend)

    logger.debug(
        "Taskiq broker configured",
        extra={"queue_name": queue_name, "result_expiry": result_expiry},
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
