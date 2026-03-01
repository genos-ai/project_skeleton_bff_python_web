"""Unit tests for event schemas and publisher."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.backend.events.publishers import NoteEventPublisher
from modules.backend.events.schemas import (
    EventEnvelope,
    NoteArchived,
    NoteCreated,
    NoteUpdated,
)


class TestEventEnvelope:
    def test_auto_generates_fields(self):
        """EventEnvelope should auto-generate event_id and timestamp."""
        event = EventEnvelope(
            event_type="test",
            source="unit",
            correlation_id="abc",
            payload={},
        )
        # event_id should be a valid UUID string
        uuid.UUID(event.event_id)
        assert event.event_version == 1
        assert "T" in event.timestamp  # ISO format

    def test_custom_fields_preserved(self):
        """Explicitly set fields should not be overridden."""
        event = EventEnvelope(
            event_id="custom-id",
            event_type="test",
            timestamp="2026-01-01T00:00:00",
            trace_id="trace-123",
            source="unit",
            correlation_id="abc",
            payload={"key": "val"},
        )
        assert event.event_id == "custom-id"
        assert event.timestamp == "2026-01-01T00:00:00"
        assert event.trace_id == "trace-123"

    def test_serializes_to_dict(self):
        """model_dump() should include all fields."""
        event = EventEnvelope(
            event_type="test",
            source="unit",
            correlation_id="abc",
            payload={"data": 1},
        )
        data = event.model_dump()
        assert "event_id" in data
        assert "event_type" in data
        assert "event_version" in data
        assert "timestamp" in data
        assert "source" in data
        assert "correlation_id" in data
        assert "payload" in data


class TestNoteEvents:
    def test_note_created_has_correct_event_type(self):
        event = NoteCreated(
            source="test", correlation_id="x", payload={},
        )
        assert event.event_type == "notes.note.created"

    def test_note_updated_has_correct_event_type(self):
        event = NoteUpdated(
            source="test", correlation_id="x", payload={},
        )
        assert event.event_type == "notes.note.updated"

    def test_note_archived_has_correct_event_type(self):
        event = NoteArchived(
            source="test", correlation_id="x", payload={},
        )
        assert event.event_type == "notes.note.archived"


class TestNoteEventPublisher:
    def test_stream_names(self):
        assert NoteEventPublisher.STREAM_CREATED == "notes:note-created"
        assert NoteEventPublisher.STREAM_UPDATED == "notes:note-updated"
        assert NoteEventPublisher.STREAM_ARCHIVED == "notes:note-archived"

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self):
        """Publisher should not call broker.publish when feature is disabled."""
        mock_config = MagicMock()
        mock_config.features.events_publish_enabled = False

        with patch(
            "modules.backend.core.config.get_app_config",
            return_value=mock_config,
        ):
            publisher = NoteEventPublisher()
            await publisher.note_created(
                note_id="123", title="Test", correlation_id="req-1",
            )

    @pytest.mark.asyncio
    async def test_publishes_when_enabled(self):
        """Publisher should call broker.publish with correct stream when enabled."""
        mock_config = MagicMock()
        mock_config.features.events_publish_enabled = True

        mock_broker = AsyncMock()

        with patch(
            "modules.backend.core.config.get_app_config",
            return_value=mock_config,
        ), patch(
            "modules.backend.events.broker.get_event_broker",
            return_value=mock_broker,
        ):
            publisher = NoteEventPublisher()
            await publisher.note_created(
                note_id="note-1", title="Hello", correlation_id="req-2",
            )

            mock_broker.publish.assert_called_once()
            call_args = mock_broker.publish.call_args
            payload = call_args[0][0]
            assert payload["event_type"] == "notes.note.created"
            assert payload["payload"]["note_id"] == "note-1"
            assert call_args[1]["channel"] == "notes:note-created"

    @pytest.mark.asyncio
    async def test_publishes_updated_event(self):
        """Publisher should publish note updated events."""
        mock_config = MagicMock()
        mock_config.features.events_publish_enabled = True

        mock_broker = AsyncMock()

        with patch(
            "modules.backend.core.config.get_app_config",
            return_value=mock_config,
        ), patch(
            "modules.backend.events.broker.get_event_broker",
            return_value=mock_broker,
        ):
            publisher = NoteEventPublisher()
            await publisher.note_updated(
                note_id="note-1", fields=["title"], correlation_id="req-3",
            )

            call_args = mock_broker.publish.call_args
            payload = call_args[0][0]
            assert payload["event_type"] == "notes.note.updated"
            assert call_args[1]["channel"] == "notes:note-updated"

    @pytest.mark.asyncio
    async def test_publishes_archived_event(self):
        """Publisher should publish note archived events."""
        mock_config = MagicMock()
        mock_config.features.events_publish_enabled = True

        mock_broker = AsyncMock()

        with patch(
            "modules.backend.core.config.get_app_config",
            return_value=mock_config,
        ), patch(
            "modules.backend.events.broker.get_event_broker",
            return_value=mock_broker,
        ):
            publisher = NoteEventPublisher()
            await publisher.note_archived(
                note_id="note-1", correlation_id="req-4",
            )

            call_args = mock_broker.publish.call_args
            payload = call_args[0][0]
            assert payload["event_type"] == "notes.note.archived"
            assert call_args[1]["channel"] == "notes:note-archived"
