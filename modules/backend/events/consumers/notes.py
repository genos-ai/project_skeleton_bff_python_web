"""
Note Event Consumer.

Subscribes to note domain events and processes them with the full
resilience stack: circuit breaker → retry → timeout.
Failed events are routed to a dead letter queue (DLQ) after retries
are exhausted.

This is a reference implementation showing the consumer pattern.
In a real application, the handler would trigger downstream actions
(search indexing, notifications, analytics, etc.).

Run with: python cli.py --service event-worker
"""

import asyncio

import aiobreaker
from faststream.redis import StreamSub
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from modules.backend.core.logging import get_logger
from modules.backend.core.resilience import ResilienceLogger, log_retry
from modules.backend.events.broker import get_event_broker
from modules.backend.events.schemas import EventEnvelope

logger = get_logger(__name__)

broker = get_event_broker()

_note_consumer_breaker = aiobreaker.CircuitBreaker(
    fail_max=5,
    timeout_duration=30,
    listeners=[ResilienceLogger("note-consumer")],
)


async def _send_to_dlq(stream: str, event: EventEnvelope, error: Exception) -> None:
    """Publish a failed event to the dead letter queue stream.

    DLQ stream name follows the convention: dlq:{original_stream}
    The original event is preserved with added error metadata.
    """
    from modules.backend.core.config import get_app_config

    dlq_config = get_app_config().events.dlq
    if not dlq_config.enabled:
        return

    dlq_stream = f"{dlq_config.stream_prefix}:{stream}"
    dlq_payload = event.model_dump()
    dlq_payload["_dlq_error"] = str(error)
    dlq_payload["_dlq_original_stream"] = stream

    try:
        await broker.publish(dlq_payload, channel=dlq_stream)
        logger.warning(
            "Event sent to DLQ",
            extra={
                "dlq_stream": dlq_stream,
                "event_id": event.event_id,
                "error": str(error),
            },
        )
    except Exception as dlq_err:
        logger.error(
            "Failed to send event to DLQ",
            extra={
                "dlq_stream": dlq_stream,
                "event_id": event.event_id,
                "dlq_error": str(dlq_err),
                "original_error": str(error),
            },
        )


async def _handle_event(stream: str, event: EventEnvelope) -> None:
    """Process an event with resilience, routing failures to the DLQ."""
    try:
        await _process_note_event_with_resilience(event)
    except Exception as exc:
        logger.error(
            "Event processing failed after retries",
            extra={
                "event_type": event.event_type,
                "event_id": event.event_id,
                "error": str(exc),
            },
        )
        await _send_to_dlq(stream, event, exc)


@broker.subscriber(stream=StreamSub("notes:note-created", group="note-processor", consumer="note-consumer-1"))
async def handle_note_created(data: dict) -> None:
    """Process a notes.note.created event.

    Demonstrates the consumer pattern with:
    - Event envelope parsing
    - Resilience stack (circuit breaker + retry + timeout)
    - DLQ routing on terminal failure
    - Structured logging with correlation context
    """
    event = EventEnvelope(**data)

    logger.info(
        "Processing note created event",
        extra={
            "note_id": event.payload.get("note_id"),
            "title": event.payload.get("title"),
            "correlation_id": event.correlation_id,
        },
    )

    await _handle_event("notes:note-created", event)


@broker.subscriber(stream=StreamSub("notes:note-updated", group="note-processor", consumer="note-consumer-1"))
async def handle_note_updated(data: dict) -> None:
    """Process a notes.note.updated event."""
    event = EventEnvelope(**data)

    logger.info(
        "Processing note updated event",
        extra={
            "note_id": event.payload.get("note_id"),
            "fields": event.payload.get("fields_updated"),
            "correlation_id": event.correlation_id,
        },
    )

    await _handle_event("notes:note-updated", event)


@broker.subscriber(stream=StreamSub("notes:note-archived", group="note-processor", consumer="note-consumer-1"))
async def handle_note_archived(data: dict) -> None:
    """Process a notes.note.archived event."""
    event = EventEnvelope(**data)

    logger.info(
        "Processing note archived event",
        extra={
            "note_id": event.payload.get("note_id"),
            "correlation_id": event.correlation_id,
        },
    )

    await _handle_event("notes:note-archived", event)


@_note_consumer_breaker
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    before_sleep=log_retry,
    reraise=True,
)
async def _process_note_event_with_resilience(event: EventEnvelope) -> None:
    """Process event with the full resilience stack.

    In a real application, this would call downstream services
    (search indexing, notification dispatch, analytics pipeline).
    The circuit breaker + retry + timeout pattern protects against
    downstream failures. If this raises after all retries, the caller
    routes the event to the DLQ.
    """
    async with asyncio.timeout(30):
        logger.info(
            "Note event processed successfully",
            extra={
                "event_type": event.event_type,
                "event_id": event.event_id,
            },
        )
