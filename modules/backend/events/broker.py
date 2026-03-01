"""
Event Broker.

FastStream RedisBroker setup with lazy initialization.
The broker connects to the same Redis instance used by Taskiq and caching.

Usage:
    from modules.backend.events.broker import get_event_broker

    broker = get_event_broker()
"""

from faststream import FastStream
from faststream.redis import RedisBroker

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

_broker: RedisBroker | None = None
_app: FastStream | None = None


def create_event_broker() -> RedisBroker:
    """Create a new RedisBroker using the project's Redis URL.

    Returns:
        Configured RedisBroker instance
    """
    from modules.backend.core.config import get_redis_url

    redis_url = get_redis_url()
    broker = RedisBroker(redis_url)
    logger.info("Event broker created")
    return broker


def get_event_broker() -> RedisBroker:
    """Get the shared event broker (lazy initialization).

    Returns:
        Shared RedisBroker instance
    """
    global _broker
    if _broker is None:
        _broker = create_event_broker()
    return _broker


def create_event_app() -> FastStream:
    """Create a FastStream application for the event worker process.

    This is a factory function — FastStream CLI must be invoked with `--factory`:
        faststream run --factory modules.backend.events.broker:create_event_app

    Returns:
        FastStream app with broker and consumers registered
    """
    global _app
    if _app is not None:
        return _app

    broker = get_event_broker()

    from modules.backend.events.middleware import EventObservabilityMiddleware
    broker.middlewares = [EventObservabilityMiddleware]

    from modules.backend.events.consumers import notes as _notes_consumer  # noqa: F841

    _app = FastStream(broker)
    logger.info("Event worker application created")
    return _app
