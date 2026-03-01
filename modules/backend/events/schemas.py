"""
Event Schemas.

Standardized event envelope and domain-specific event types.
All events published through the event bus use the EventEnvelope base.

Naming convention for event_type: domain.entity.action (dot notation)
Stream naming convention: {domain}:{event-type} (colon-separated)

Usage:
    from modules.backend.events.schemas import NoteCreated

    event = NoteCreated(
        source="note-service",
        correlation_id=request_id,
        payload={"id": note.id, "title": note.title},
    )
"""

from uuid import uuid4

from pydantic import BaseModel, Field

from modules.backend.core.utils import utc_now


class EventEnvelope(BaseModel):
    """Base event envelope — all events inherit from this.

    Fields:
        event_id: Unique event identifier (auto-generated UUID)
        event_type: Domain event type in dot notation (e.g. notes.note.created)
        event_version: Schema version for forward compatibility
        timestamp: ISO 8601 UTC timestamp
        source: Service/module that published the event
        correlation_id: Request/session ID for tracing across services
        trace_id: OpenTelemetry trace ID (optional, populated when tracing is active)
        payload: Event-specific data
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    event_version: int = 1
    timestamp: str = Field(default_factory=lambda: utc_now().isoformat())
    source: str
    correlation_id: str
    trace_id: str | None = None
    payload: dict


class NoteCreated(EventEnvelope):
    """Published when a new note is created."""

    event_type: str = "notes.note.created"


class NoteUpdated(EventEnvelope):
    """Published when a note is updated."""

    event_type: str = "notes.note.updated"


class NoteArchived(EventEnvelope):
    """Published when a note is archived."""

    event_type: str = "notes.note.archived"
