"""
Event Publishers.

Domain-specific event publishers. Each publisher wraps the broker's
publish() method with the correct stream name and event schema.

Publishers check the events_publish_enabled feature flag before publishing.
When disabled, events are silently skipped (no error, no log noise).

Usage:
    from modules.backend.events.publishers import NoteEventPublisher

    publisher = NoteEventPublisher()
    await publisher.note_created(note, correlation_id=request_id)
"""

from modules.backend.core.logging import get_logger
from modules.backend.events.schemas import NoteArchived, NoteCreated, NoteUpdated

logger = get_logger(__name__)


def _get_trace_id() -> str | None:
    """Extract current OpenTelemetry trace ID if available."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            return format(span.get_span_context().trace_id, "032x")
    except ImportError:
        pass
    return None


class NoteEventPublisher:
    """Publishes note domain events to Redis Streams."""

    STREAM_CREATED = "notes:note-created"
    STREAM_UPDATED = "notes:note-updated"
    STREAM_ARCHIVED = "notes:note-archived"

    async def note_created(
        self, note_id: str, title: str, correlation_id: str,
    ) -> None:
        """Publish a notes.note.created event."""
        await self._publish(
            self.STREAM_CREATED,
            NoteCreated(
                source="note-service",
                correlation_id=correlation_id,
                trace_id=_get_trace_id(),
                payload={"note_id": note_id, "title": title},
            ),
        )

    async def note_updated(
        self, note_id: str, fields: list[str], correlation_id: str,
    ) -> None:
        """Publish a notes.note.updated event."""
        await self._publish(
            self.STREAM_UPDATED,
            NoteUpdated(
                source="note-service",
                correlation_id=correlation_id,
                trace_id=_get_trace_id(),
                payload={"note_id": note_id, "fields_updated": fields},
            ),
        )

    async def note_archived(
        self, note_id: str, correlation_id: str,
    ) -> None:
        """Publish a notes.note.archived event."""
        await self._publish(
            self.STREAM_ARCHIVED,
            NoteArchived(
                source="note-service",
                correlation_id=correlation_id,
                trace_id=_get_trace_id(),
                payload={"note_id": note_id},
            ),
        )

    async def _publish(self, stream: str, event) -> None:
        """Publish an event if the feature flag is enabled."""
        from modules.backend.core.config import get_app_config

        if not get_app_config().features.events_publish_enabled:
            return

        from modules.backend.events.broker import get_event_broker

        broker = get_event_broker()
        await broker.publish(event.model_dump(), channel=stream)
        logger.debug(
            "Event published",
            extra={"stream": stream, "event_type": event.event_type, "event_id": event.event_id},
        )
