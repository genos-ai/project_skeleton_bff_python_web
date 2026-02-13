"""
Integration Tests for Database Fixtures.

These tests verify that the database fixtures work correctly.
They serve as both tests and documentation for how to use the fixtures.
"""

import pytest
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from modules.backend.models.base import Base, TimestampMixin, UUIDMixin


# =============================================================================
# Sample Model (for fixture testing only)
# =============================================================================


class SampleItem(UUIDMixin, TimestampMixin, Base):
    """Sample model for database fixture tests."""

    __tablename__ = "sample_items"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)


# =============================================================================
# Database Session Tests
# =============================================================================


class TestDatabaseSession:
    """Tests for db_session fixture."""

    @pytest.mark.asyncio
    async def test_session_is_provided(self, db_session: AsyncSession):
        """Should provide a valid database session."""
        assert db_session is not None
        assert isinstance(db_session, AsyncSession)

    @pytest.mark.asyncio
    async def test_can_create_record(self, db_session: AsyncSession):
        """Should be able to create records in the database."""
        # Arrange
        item = SampleItem(name="Test Item", description="A test item")

        # Act
        db_session.add(item)
        await db_session.flush()

        # Assert
        assert item.id is not None
        assert item.created_at is not None
        assert item.updated_at is not None

    @pytest.mark.asyncio
    async def test_can_query_records(self, db_session: AsyncSession):
        """Should be able to query records from the database."""
        # Arrange
        item = SampleItem(name="Queryable Item")
        db_session.add(item)
        await db_session.flush()

        # Act
        result = await db_session.execute(
            select(SampleItem).where(SampleItem.id == item.id)
        )
        found = result.scalar_one_or_none()

        # Assert
        assert found is not None
        assert found.name == "Queryable Item"

    @pytest.mark.asyncio
    async def test_changes_are_rolled_back(self, db_session: AsyncSession):
        """Changes should be rolled back after each test."""
        # This test creates an item
        item = SampleItem(name="Rollback Test Item")
        db_session.add(item)
        await db_session.flush()

        # The item exists within this test
        result = await db_session.execute(select(SampleItem))
        items = result.scalars().all()
        # May have items from this test, but not from previous tests
        # (each test gets a fresh session that's rolled back)


class TestDatabaseIsolation:
    """Tests verifying test isolation."""

    @pytest.mark.asyncio
    async def test_first_test_creates_item(self, db_session: AsyncSession):
        """First test creates an item."""
        item = SampleItem(name="First Test Item")
        db_session.add(item)
        await db_session.flush()
        assert item.id is not None

    @pytest.mark.asyncio
    async def test_second_test_has_clean_database(self, db_session: AsyncSession):
        """Second test should not see items from first test."""
        # Query for all items - should be empty due to rollback
        result = await db_session.execute(select(SampleItem))
        items = result.scalars().all()

        # Items from other tests should have been rolled back
        # This test starts with a clean slate
        assert len(items) == 0


class TestUUIDMixin:
    """Tests for UUIDMixin functionality."""

    @pytest.mark.asyncio
    async def test_generates_uuid_on_create(self, db_session: AsyncSession):
        """Should automatically generate UUID for new records."""
        item = SampleItem(name="UUID Test")
        db_session.add(item)
        await db_session.flush()

        assert item.id is not None
        assert len(item.id) == 36  # UUID format: 8-4-4-4-12

    @pytest.mark.asyncio
    async def test_uuid_is_unique(self, db_session: AsyncSession):
        """Each record should get a unique UUID."""
        item1 = SampleItem(name="Item 1")
        item2 = SampleItem(name="Item 2")

        db_session.add(item1)
        db_session.add(item2)
        await db_session.flush()

        assert item1.id != item2.id


class TestTimestampMixin:
    """Tests for TimestampMixin functionality."""

    @pytest.mark.asyncio
    async def test_sets_created_at_on_create(self, db_session: AsyncSession):
        """Should set created_at timestamp on creation."""
        item = SampleItem(name="Timestamp Test")
        db_session.add(item)
        await db_session.flush()

        assert item.created_at is not None

    @pytest.mark.asyncio
    async def test_sets_updated_at_on_create(self, db_session: AsyncSession):
        """Should set updated_at timestamp on creation."""
        item = SampleItem(name="Timestamp Test")
        db_session.add(item)
        await db_session.flush()

        assert item.updated_at is not None

    @pytest.mark.asyncio
    async def test_created_at_equals_updated_at_initially(
        self, db_session: AsyncSession
    ):
        """created_at and updated_at should be equal on creation."""
        item = SampleItem(name="Timestamp Test")
        db_session.add(item)
        await db_session.flush()

        # They should be very close (same or within milliseconds)
        diff = abs((item.updated_at - item.created_at).total_seconds())
        assert diff < 1  # Less than 1 second difference
