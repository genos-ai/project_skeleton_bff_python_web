"""Unit tests for event consumers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.backend.events.schemas import EventEnvelope


def _make_event_dict(**overrides) -> dict:
    """Create a valid event dict for testing."""
    base = {
        "event_id": "evt-123",
        "event_type": "notes.note.created",
        "event_version": 1,
        "timestamp": "2026-01-01T00:00:00",
        "source": "test",
        "correlation_id": "req-abc",
        "trace_id": None,
        "payload": {"note_id": "note-1", "title": "Test Note"},
    }
    base.update(overrides)
    return base


class TestHandleNoteCreated:
    @pytest.mark.asyncio
    async def test_processes_event(self):
        """handle_note_created should process a valid event dict."""
        from modules.backend.events.consumers.notes import handle_note_created

        with patch(
            "modules.backend.events.consumers.notes._handle_event",
            new_callable=AsyncMock,
        ) as mock_handle:
            await handle_note_created(_make_event_dict())
            mock_handle.assert_called_once()
            call_args = mock_handle.call_args
            assert call_args[0][0] == "notes:note-created"
            assert isinstance(call_args[0][1], EventEnvelope)


class TestHandleNoteUpdated:
    @pytest.mark.asyncio
    async def test_processes_event(self):
        """handle_note_updated should process a valid event dict."""
        from modules.backend.events.consumers.notes import handle_note_updated

        data = _make_event_dict(
            event_type="notes.note.updated",
            payload={"note_id": "note-1", "fields_updated": ["title"]},
        )
        with patch(
            "modules.backend.events.consumers.notes._handle_event",
            new_callable=AsyncMock,
        ) as mock_handle:
            await handle_note_updated(data)
            mock_handle.assert_called_once()


class TestHandleNoteArchived:
    @pytest.mark.asyncio
    async def test_processes_event(self):
        """handle_note_archived should process a valid event dict."""
        from modules.backend.events.consumers.notes import handle_note_archived

        data = _make_event_dict(
            event_type="notes.note.archived",
            payload={"note_id": "note-1"},
        )
        with patch(
            "modules.backend.events.consumers.notes._handle_event",
            new_callable=AsyncMock,
        ) as mock_handle:
            await handle_note_archived(data)
            mock_handle.assert_called_once()


class TestProcessWithResilience:
    @pytest.mark.asyncio
    async def test_succeeds(self):
        """_process_note_event_with_resilience should complete without error."""
        from modules.backend.events.consumers.notes import (
            _process_note_event_with_resilience,
        )

        event = EventEnvelope(**_make_event_dict())
        # Should not raise
        await _process_note_event_with_resilience(event)


class TestSendToDlq:
    @pytest.mark.asyncio
    async def test_publishes_on_failure(self):
        """Failed events should be sent to the DLQ stream."""
        from modules.backend.events.consumers.notes import _send_to_dlq

        mock_config = MagicMock()
        mock_config.events.dlq.enabled = True
        mock_config.events.dlq.stream_prefix = "dlq"

        mock_broker = AsyncMock()

        event = EventEnvelope(**_make_event_dict())
        error = RuntimeError("processing failed")

        with patch(
            "modules.backend.core.config.get_app_config",
            return_value=mock_config,
        ), patch(
            "modules.backend.events.consumers.notes.broker",
            mock_broker,
        ):
            await _send_to_dlq("notes:note-created", event, error)

            mock_broker.publish.assert_called_once()
            call_args = mock_broker.publish.call_args
            payload = call_args[0][0]
            assert payload["_dlq_error"] == "processing failed"
            assert payload["_dlq_original_stream"] == "notes:note-created"
            assert call_args[1]["channel"] == "dlq:notes:note-created"

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self):
        """DLQ publishing should be skipped when dlq.enabled is False."""
        from modules.backend.events.consumers.notes import _send_to_dlq

        mock_config = MagicMock()
        mock_config.events.dlq.enabled = False

        mock_broker = AsyncMock()

        event = EventEnvelope(**_make_event_dict())

        with patch(
            "modules.backend.core.config.get_app_config",
            return_value=mock_config,
        ), patch(
            "modules.backend.events.consumers.notes.broker",
            mock_broker,
        ):
            await _send_to_dlq("notes:note-created", event, RuntimeError("fail"))
            mock_broker.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_error_on_publish_failure(self):
        """If DLQ publish itself fails, it should log but not raise."""
        from modules.backend.events.consumers.notes import _send_to_dlq

        mock_config = MagicMock()
        mock_config.events.dlq.enabled = True
        mock_config.events.dlq.stream_prefix = "dlq"

        mock_broker = AsyncMock()
        mock_broker.publish.side_effect = ConnectionError("redis down")

        event = EventEnvelope(**_make_event_dict())

        with patch(
            "modules.backend.core.config.get_app_config",
            return_value=mock_config,
        ), patch(
            "modules.backend.events.consumers.notes.broker",
            mock_broker,
        ), patch(
            "modules.backend.events.consumers.notes.logger",
        ) as mock_logger:
            await _send_to_dlq("notes:note-created", event, RuntimeError("original"))
            mock_logger.error.assert_called_once()


class TestHandleEvent:
    @pytest.mark.asyncio
    async def test_routes_to_dlq_on_failure(self):
        """_handle_event should route to DLQ when processing fails."""
        from modules.backend.events.consumers.notes import _handle_event

        event = EventEnvelope(**_make_event_dict())

        with patch(
            "modules.backend.events.consumers.notes._process_note_event_with_resilience",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ), patch(
            "modules.backend.events.consumers.notes._send_to_dlq",
            new_callable=AsyncMock,
        ) as mock_dlq:
            await _handle_event("notes:note-created", event)
            mock_dlq.assert_called_once()
            assert mock_dlq.call_args[0][0] == "notes:note-created"
