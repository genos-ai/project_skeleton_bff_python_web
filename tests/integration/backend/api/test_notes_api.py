"""
Integration Tests for Notes API.

Tests the notes API endpoints with a real database.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.models.note import Note


class TestCreateNote:
    """Tests for POST /api/v1/notes."""

    @pytest.mark.asyncio
    async def test_create_note_success(
        self,
        client: AsyncClient,
        api,
    ):
        """Should create a note and return it."""
        response = await client.post(
            "/api/v1/notes",
            json={"title": "Test Note", "content": "Test content"},
        )

        data = api.assert_success(response, expected_status=201)
        assert data["data"]["title"] == "Test Note"
        assert data["data"]["content"] == "Test content"
        assert data["data"]["is_archived"] is False
        assert "id" in data["data"]
        assert "created_at" in data["data"]

    @pytest.mark.asyncio
    async def test_create_note_without_content(
        self,
        client: AsyncClient,
        api,
    ):
        """Should create a note with only title."""
        response = await client.post(
            "/api/v1/notes",
            json={"title": "Title Only"},
        )

        data = api.assert_success(response, expected_status=201)
        assert data["data"]["title"] == "Title Only"
        assert data["data"]["content"] is None

    @pytest.mark.asyncio
    async def test_create_note_empty_title_fails(
        self,
        client: AsyncClient,
        api,
    ):
        """Should reject empty title."""
        response = await client.post(
            "/api/v1/notes",
            json={"title": ""},
        )

        api.assert_validation_error(response, field="title")

    @pytest.mark.asyncio
    async def test_create_note_missing_title_fails(
        self,
        client: AsyncClient,
        api,
    ):
        """Should reject missing title."""
        response = await client.post(
            "/api/v1/notes",
            json={"content": "Content without title"},
        )

        api.assert_validation_error(response, field="title")


class TestGetNote:
    """Tests for GET /api/v1/notes/{note_id}."""

    @pytest.mark.asyncio
    async def test_get_note_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        api,
    ):
        """Should return a note by ID."""
        # Create a note directly in the database
        note = Note(title="Get Test", content="Content")
        db_session.add(note)
        await db_session.flush()

        response = await client.get(f"/api/v1/notes/{note.id}")

        data = api.assert_success(response)
        assert data["data"]["id"] == note.id
        assert data["data"]["title"] == "Get Test"

    @pytest.mark.asyncio
    async def test_get_note_not_found(
        self,
        client: AsyncClient,
        api,
    ):
        """Should return 404 for nonexistent note."""
        response = await client.get("/api/v1/notes/nonexistent-id")

        api.assert_error(response, 404, "RES_NOT_FOUND")


class TestListNotes:
    """Tests for GET /api/v1/notes."""

    @pytest.mark.asyncio
    async def test_list_notes_empty(
        self,
        client: AsyncClient,
        api,
    ):
        """Should return empty list when no notes."""
        response = await client.get("/api/v1/notes")

        data = api.assert_success(response)
        assert data["data"] == []

    @pytest.mark.asyncio
    async def test_list_notes_returns_active_only(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        api,
    ):
        """Should return only active notes by default."""
        # Create active and archived notes
        active = Note(title="Active Note", is_archived=False)
        archived = Note(title="Archived Note", is_archived=True)
        db_session.add(active)
        db_session.add(archived)
        await db_session.flush()

        response = await client.get("/api/v1/notes")

        data = api.assert_success(response)
        assert len(data["data"]) == 1
        assert data["data"][0]["title"] == "Active Note"

    @pytest.mark.asyncio
    async def test_list_notes_include_archived(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        api,
    ):
        """Should include archived notes when requested."""
        active = Note(title="Active", is_archived=False)
        archived = Note(title="Archived", is_archived=True)
        db_session.add(active)
        db_session.add(archived)
        await db_session.flush()

        response = await client.get("/api/v1/notes?include_archived=true")

        data = api.assert_success(response)
        assert len(data["data"]) == 2

    @pytest.mark.asyncio
    async def test_list_notes_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        api,
    ):
        """Should support pagination."""
        # Create multiple notes
        for i in range(5):
            db_session.add(Note(title=f"Note {i}"))
        await db_session.flush()

        response = await client.get("/api/v1/notes?limit=2&offset=0")

        data = api.assert_success(response)
        assert len(data["data"]) == 2


class TestUpdateNote:
    """Tests for PATCH /api/v1/notes/{note_id}."""

    @pytest.mark.asyncio
    async def test_update_note_title(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        api,
    ):
        """Should update note title."""
        note = Note(title="Original Title")
        db_session.add(note)
        await db_session.flush()

        response = await client.patch(
            f"/api/v1/notes/{note.id}",
            json={"title": "Updated Title"},
        )

        data = api.assert_success(response)
        assert data["data"]["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_update_note_content(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        api,
    ):
        """Should update note content."""
        note = Note(title="Test", content="Original")
        db_session.add(note)
        await db_session.flush()

        response = await client.patch(
            f"/api/v1/notes/{note.id}",
            json={"content": "Updated content"},
        )

        data = api.assert_success(response)
        assert data["data"]["content"] == "Updated content"

    @pytest.mark.asyncio
    async def test_update_note_not_found(
        self,
        client: AsyncClient,
        api,
    ):
        """Should return 404 for nonexistent note."""
        response = await client.patch(
            "/api/v1/notes/nonexistent",
            json={"title": "New Title"},
        )

        api.assert_error(response, 404, "RES_NOT_FOUND")


class TestDeleteNote:
    """Tests for DELETE /api/v1/notes/{note_id}."""

    @pytest.mark.asyncio
    async def test_delete_note_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Should delete a note."""
        note = Note(title="To Delete")
        db_session.add(note)
        await db_session.flush()
        note_id = note.id

        response = await client.delete(f"/api/v1/notes/{note_id}")

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_note_not_found(
        self,
        client: AsyncClient,
        api,
    ):
        """Should return 404 for nonexistent note."""
        response = await client.delete("/api/v1/notes/nonexistent")

        api.assert_error(response, 404, "RES_NOT_FOUND")


class TestArchiveNote:
    """Tests for POST /api/v1/notes/{note_id}/archive."""

    @pytest.mark.asyncio
    async def test_archive_note_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        api,
    ):
        """Should archive a note."""
        note = Note(title="To Archive", is_archived=False)
        db_session.add(note)
        await db_session.flush()

        response = await client.post(f"/api/v1/notes/{note.id}/archive")

        data = api.assert_success(response)
        assert data["data"]["is_archived"] is True

    @pytest.mark.asyncio
    async def test_unarchive_note_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        api,
    ):
        """Should unarchive a note."""
        note = Note(title="To Unarchive", is_archived=True)
        db_session.add(note)
        await db_session.flush()

        response = await client.post(f"/api/v1/notes/{note.id}/unarchive")

        data = api.assert_success(response)
        assert data["data"]["is_archived"] is False


class TestSearchNotes:
    """Tests for GET /api/v1/notes/search."""

    @pytest.mark.asyncio
    async def test_search_notes_by_title(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        api,
    ):
        """Should find notes matching search query."""
        db_session.add(Note(title="Python Tutorial"))
        db_session.add(Note(title="JavaScript Guide"))
        db_session.add(Note(title="Python Advanced"))
        await db_session.flush()

        response = await client.get("/api/v1/notes/search?q=Python")

        data = api.assert_success(response)
        assert len(data["data"]) == 2
        titles = [n["title"] for n in data["data"]]
        assert "Python Tutorial" in titles
        assert "Python Advanced" in titles

    @pytest.mark.asyncio
    async def test_search_notes_case_insensitive(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        api,
    ):
        """Should search case-insensitively."""
        db_session.add(Note(title="UPPERCASE"))
        db_session.add(Note(title="lowercase"))
        await db_session.flush()

        response = await client.get("/api/v1/notes/search?q=upper")

        data = api.assert_success(response)
        assert len(data["data"]) == 1

    @pytest.mark.asyncio
    async def test_search_notes_excludes_archived(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        api,
    ):
        """Should exclude archived notes from search."""
        db_session.add(Note(title="Active Match", is_archived=False))
        db_session.add(Note(title="Archived Match", is_archived=True))
        await db_session.flush()

        response = await client.get("/api/v1/notes/search?q=Match")

        data = api.assert_success(response)
        assert len(data["data"]) == 1
        assert data["data"][0]["title"] == "Active Match"

    @pytest.mark.asyncio
    async def test_search_notes_empty_query_fails(
        self,
        client: AsyncClient,
        api,
    ):
        """Should reject empty search query."""
        response = await client.get("/api/v1/notes/search?q=")

        api.assert_validation_error(response)
