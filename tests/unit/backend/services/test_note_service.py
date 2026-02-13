"""
Unit Tests for Note Service.

Tests the NoteService business logic with mocked dependencies.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from modules.backend.services.note import NoteService
from modules.backend.schemas.note import NoteCreate, NoteUpdate
from modules.backend.core.exceptions import NotFoundError


class TestNoteServiceCreate:
    """Tests for note creation."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        """Create NoteService with mocked session."""
        return NoteService(mock_session)

    @pytest.mark.asyncio
    async def test_create_note_success(self, service):
        """Should create a note with title and content."""
        # Arrange
        mock_note = MagicMock()
        mock_note.id = "note-123"
        mock_note.title = "Test Note"
        mock_note.content = "Test content"

        with patch.object(service.repo, "create", return_value=mock_note) as mock_create:
            # Act
            data = NoteCreate(title="Test Note", content="Test content")
            result = await service.create_note(data)

            # Assert
            mock_create.assert_called_once_with(
                title="Test Note",
                content="Test content",
            )
            assert result.id == "note-123"

    @pytest.mark.asyncio
    async def test_create_note_without_content(self, service):
        """Should create a note with only title."""
        mock_note = MagicMock()
        mock_note.id = "note-456"

        with patch.object(service.repo, "create", return_value=mock_note):
            data = NoteCreate(title="Title Only")
            result = await service.create_note(data)

            assert result.id == "note-456"


class TestNoteServiceGet:
    """Tests for getting notes."""

    @pytest.fixture
    def service(self):
        """Create NoteService with mocked session."""
        return NoteService(AsyncMock())

    @pytest.mark.asyncio
    async def test_get_note_success(self, service):
        """Should return note when found."""
        mock_note = MagicMock()
        mock_note.id = "note-123"
        mock_note.title = "Found Note"

        with patch.object(service.repo, "get_by_id", return_value=mock_note):
            result = await service.get_note("note-123")

            assert result.id == "note-123"
            assert result.title == "Found Note"

    @pytest.mark.asyncio
    async def test_get_note_not_found(self, service):
        """Should raise NotFoundError when note doesn't exist."""
        with patch.object(
            service.repo, "get_by_id", side_effect=NotFoundError("Note not found")
        ):
            with pytest.raises(NotFoundError):
                await service.get_note("nonexistent")


class TestNoteServiceList:
    """Tests for listing notes."""

    @pytest.fixture
    def service(self):
        """Create NoteService with mocked session."""
        return NoteService(AsyncMock())

    @pytest.mark.asyncio
    async def test_list_notes_active_only(self, service):
        """Should list only active notes by default."""
        mock_notes = [MagicMock(), MagicMock()]

        with patch.object(
            service.repo, "get_all_active", return_value=mock_notes
        ) as mock_get:
            result = await service.list_notes()

            mock_get.assert_called_once_with(limit=50, offset=0)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_notes_include_archived(self, service):
        """Should include archived notes when requested."""
        mock_notes = [MagicMock(), MagicMock(), MagicMock()]

        with patch.object(service.repo, "get_all", return_value=mock_notes) as mock_get:
            result = await service.list_notes(include_archived=True)

            mock_get.assert_called_once_with(limit=50, offset=0)
            assert len(result) == 3

    @pytest.mark.asyncio
    async def test_list_notes_with_pagination(self, service):
        """Should pass pagination parameters."""
        with patch.object(service.repo, "get_all_active", return_value=[]) as mock_get:
            await service.list_notes(limit=10, offset=20)

            mock_get.assert_called_once_with(limit=10, offset=20)


class TestNoteServiceUpdate:
    """Tests for updating notes."""

    @pytest.fixture
    def service(self):
        """Create NoteService with mocked session."""
        return NoteService(AsyncMock())

    @pytest.mark.asyncio
    async def test_update_note_title(self, service):
        """Should update note title."""
        mock_note = MagicMock()
        mock_note.id = "note-123"
        mock_note.title = "Updated Title"

        with patch.object(service.repo, "update", return_value=mock_note) as mock_update:
            data = NoteUpdate(title="Updated Title")
            result = await service.update_note("note-123", data)

            mock_update.assert_called_once_with("note-123", title="Updated Title")
            assert result.title == "Updated Title"

    @pytest.mark.asyncio
    async def test_update_note_multiple_fields(self, service):
        """Should update multiple fields at once."""
        mock_note = MagicMock()

        with patch.object(service.repo, "update", return_value=mock_note) as mock_update:
            data = NoteUpdate(title="New Title", content="New Content", is_archived=True)
            await service.update_note("note-123", data)

            mock_update.assert_called_once_with(
                "note-123",
                title="New Title",
                content="New Content",
                is_archived=True,
            )

    @pytest.mark.asyncio
    async def test_update_note_no_changes(self, service):
        """Should return existing note when no fields provided."""
        mock_note = MagicMock()

        with patch.object(service.repo, "get_by_id", return_value=mock_note):
            with patch.object(service.repo, "update") as mock_update:
                data = NoteUpdate()  # No fields set
                result = await service.update_note("note-123", data)

                mock_update.assert_not_called()
                assert result is mock_note


class TestNoteServiceDelete:
    """Tests for deleting notes."""

    @pytest.fixture
    def service(self):
        """Create NoteService with mocked session."""
        return NoteService(AsyncMock())

    @pytest.mark.asyncio
    async def test_delete_note_success(self, service):
        """Should delete note."""
        with patch.object(service.repo, "delete", return_value=None) as mock_delete:
            await service.delete_note("note-123")

            mock_delete.assert_called_once_with("note-123")

    @pytest.mark.asyncio
    async def test_delete_note_not_found(self, service):
        """Should raise NotFoundError when note doesn't exist."""
        with patch.object(
            service.repo, "delete", side_effect=NotFoundError("Note not found")
        ):
            with pytest.raises(NotFoundError):
                await service.delete_note("nonexistent")


class TestNoteServiceArchive:
    """Tests for archiving notes."""

    @pytest.fixture
    def service(self):
        """Create NoteService with mocked session."""
        return NoteService(AsyncMock())

    @pytest.mark.asyncio
    async def test_archive_note(self, service):
        """Should archive a note."""
        mock_note = MagicMock()
        mock_note.is_archived = True

        with patch.object(service.repo, "archive", return_value=mock_note):
            result = await service.archive_note("note-123")

            assert result.is_archived is True

    @pytest.mark.asyncio
    async def test_unarchive_note(self, service):
        """Should unarchive a note."""
        mock_note = MagicMock()
        mock_note.is_archived = False

        with patch.object(service.repo, "unarchive", return_value=mock_note):
            result = await service.unarchive_note("note-123")

            assert result.is_archived is False


class TestNoteServiceSearch:
    """Tests for searching notes."""

    @pytest.fixture
    def service(self):
        """Create NoteService with mocked session."""
        return NoteService(AsyncMock())

    @pytest.mark.asyncio
    async def test_search_notes(self, service):
        """Should search notes by title."""
        mock_notes = [MagicMock(), MagicMock()]

        with patch.object(
            service.repo, "search_by_title", return_value=mock_notes
        ) as mock_search:
            result = await service.search_notes("test query")

            mock_search.assert_called_once_with("test query", limit=50)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_search_notes_with_limit(self, service):
        """Should pass limit to search."""
        with patch.object(service.repo, "search_by_title", return_value=[]):
            await service.search_notes("query", limit=10)

            service.repo.search_by_title.assert_called_once_with("query", limit=10)
