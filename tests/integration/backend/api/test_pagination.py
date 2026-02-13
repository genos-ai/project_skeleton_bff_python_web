"""
Integration Tests for Pagination.

Tests the pagination functionality in API endpoints.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.models.note import Note


class TestPaginatedListEndpoint:
    """Tests for paginated list endpoint."""

    @pytest.mark.asyncio
    async def test_returns_paginated_response_structure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Should return response with pagination info."""
        # Create a note
        db_session.add(Note(title="Test Note"))
        await db_session.flush()

        response = await client.get("/api/v1/notes")

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert data["success"] is True
        assert "data" in data
        assert "pagination" in data
        assert "metadata" in data

        # Check pagination fields
        pagination = data["pagination"]
        assert "total" in pagination
        assert "limit" in pagination
        assert "has_more" in pagination

    @pytest.mark.asyncio
    async def test_returns_correct_total_count(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Should return correct total count."""
        # Create 5 notes
        for i in range(5):
            db_session.add(Note(title=f"Note {i}"))
        await db_session.flush()

        response = await client.get("/api/v1/notes")

        data = response.json()
        assert data["pagination"]["total"] == 5

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Should respect limit parameter."""
        # Create 10 notes
        for i in range(10):
            db_session.add(Note(title=f"Note {i}"))
        await db_session.flush()

        response = await client.get("/api/v1/notes?limit=3")

        data = response.json()
        assert len(data["data"]) == 3
        assert data["pagination"]["limit"] == 3
        assert data["pagination"]["total"] == 10
        assert data["pagination"]["has_more"] is True

    @pytest.mark.asyncio
    async def test_respects_offset_parameter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Should respect offset parameter."""
        # Create 5 notes with distinct titles
        for i in range(5):
            db_session.add(Note(title=f"Note {i}"))
        await db_session.flush()

        # Get with offset
        response = await client.get("/api/v1/notes?limit=2&offset=2")

        data = response.json()
        assert len(data["data"]) == 2
        assert data["pagination"]["has_more"] is True

    @pytest.mark.asyncio
    async def test_has_more_false_at_end(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Should set has_more to False when at end."""
        # Create 3 notes
        for i in range(3):
            db_session.add(Note(title=f"Note {i}"))
        await db_session.flush()

        response = await client.get("/api/v1/notes?limit=10")

        data = response.json()
        assert data["pagination"]["has_more"] is False

    @pytest.mark.asyncio
    async def test_empty_results(
        self,
        client: AsyncClient,
    ):
        """Should handle empty results."""
        response = await client.get("/api/v1/notes")

        data = response.json()
        assert data["success"] is True
        assert data["data"] == []
        assert data["pagination"]["total"] == 0
        assert data["pagination"]["has_more"] is False

    @pytest.mark.asyncio
    async def test_default_limit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Should use default limit of 20."""
        # Create 25 notes
        for i in range(25):
            db_session.add(Note(title=f"Note {i}"))
        await db_session.flush()

        response = await client.get("/api/v1/notes")

        data = response.json()
        assert len(data["data"]) == 20
        assert data["pagination"]["limit"] == 20

    @pytest.mark.asyncio
    async def test_limit_validation_max(
        self,
        client: AsyncClient,
    ):
        """Should reject limit over 100."""
        response = await client.get("/api/v1/notes?limit=150")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_limit_validation_min(
        self,
        client: AsyncClient,
    ):
        """Should reject limit under 1."""
        response = await client.get("/api/v1/notes?limit=0")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_offset_validation(
        self,
        client: AsyncClient,
    ):
        """Should reject negative offset."""
        response = await client.get("/api/v1/notes?offset=-1")

        assert response.status_code == 422


class TestPaginationWithFiltering:
    """Tests for pagination combined with filtering."""

    @pytest.mark.asyncio
    async def test_pagination_excludes_archived_by_default(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Should only count active notes by default."""
        # Create 3 active and 2 archived notes
        for i in range(3):
            db_session.add(Note(title=f"Active {i}", is_archived=False))
        for i in range(2):
            db_session.add(Note(title=f"Archived {i}", is_archived=True))
        await db_session.flush()

        response = await client.get("/api/v1/notes")

        data = response.json()
        assert len(data["data"]) == 3
        assert data["pagination"]["total"] == 3

    @pytest.mark.asyncio
    async def test_pagination_includes_archived_when_requested(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Should count all notes when include_archived=true."""
        # Create 3 active and 2 archived notes
        for i in range(3):
            db_session.add(Note(title=f"Active {i}", is_archived=False))
        for i in range(2):
            db_session.add(Note(title=f"Archived {i}", is_archived=True))
        await db_session.flush()

        response = await client.get("/api/v1/notes?include_archived=true")

        data = response.json()
        assert len(data["data"]) == 5
        assert data["pagination"]["total"] == 5


class TestPaginationMetadata:
    """Tests for pagination metadata in responses."""

    @pytest.mark.asyncio
    async def test_includes_request_id(
        self,
        client: AsyncClient,
    ):
        """Should include request_id in metadata."""
        custom_id = "pagination-test-id"

        response = await client.get(
            "/api/v1/notes",
            headers={"X-Request-ID": custom_id},
        )

        data = response.json()
        assert data["metadata"]["request_id"] == custom_id

    @pytest.mark.asyncio
    async def test_includes_timestamp(
        self,
        client: AsyncClient,
    ):
        """Should include timestamp in metadata."""
        response = await client.get("/api/v1/notes")

        data = response.json()
        assert "timestamp" in data["metadata"]
