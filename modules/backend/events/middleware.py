"""
Event Observability Middleware.

Cross-cutting middleware applied to all event consumers.
Binds structlog context (correlation_id, event_type, source) for every
consumed event and measures processing duration.
"""

import time

import structlog
from faststream import BaseMiddleware

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class EventObservabilityMiddleware(BaseMiddleware):
    """Middleware that binds structlog context for event consumers.

    Applied to every message consumed from Redis Streams. Ensures that
    all log records within a consumer handler include the event's
    correlation_id and event_type for traceability.
    """

    async def on_consume(self, msg):
        # FastStream may deliver the message as a dict, a Pydantic model,
        # or a raw decoded value depending on the serializer. We extract
        # envelope fields defensively to ensure context is always bound.
        data: dict = {}
        if isinstance(msg, dict):
            data = msg
        elif hasattr(msg, "model_dump"):
            data = msg.model_dump()
        elif hasattr(msg, "__dict__"):
            data = vars(msg)

        structlog.contextvars.bind_contextvars(
            event_id=data.get("event_id", "unknown"),
            correlation_id=data.get("correlation_id", "unknown"),
            event_type=data.get("event_type", "unknown"),
            source="events",
        )
        self._start_time = time.monotonic()
        return await super().on_consume(msg)

    async def after_consume(self, err):
        duration_ms = round((time.monotonic() - self._start_time) * 1000, 1)

        if err:
            logger.error(
                "Event processing failed",
                extra={"duration_ms": duration_ms, "error": str(err)},
            )
        else:
            logger.info(
                "Event processed",
                extra={"duration_ms": duration_ms},
            )

        structlog.contextvars.unbind_contextvars(
            "event_id", "correlation_id", "event_type",
        )
        return await super().after_consume(err)
