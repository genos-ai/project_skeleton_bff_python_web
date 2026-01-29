"""
Unit Test Fixtures.

Fixtures for unit tests - all external dependencies are mocked.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Mock database session for unit tests."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_redis() -> MagicMock:
    """Mock Redis client for unit tests."""
    return MagicMock()
