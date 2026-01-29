"""
Integration Test Fixtures.

Fixtures for integration tests - uses real database and services.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

# Uncomment when database is configured:
# from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
# from modules.backend.models.base import Base


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create a test client for API integration testing."""
    from modules.backend.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


# Uncomment when database is configured:
#
# @pytest.fixture(scope="session")
# async def db_engine():
#     """Create test database engine."""
#     # Use a separate test database
#     engine = create_async_engine(
#         "postgresql+asyncpg://test:test@localhost/test_db",
#         echo=False,
#     )
#     async with engine.begin() as conn:
#         await conn.run_sync(Base.metadata.create_all)
#     yield engine
#     async with engine.begin() as conn:
#         await conn.run_sync(Base.metadata.drop_all)
#     await engine.dispose()
#
#
# @pytest.fixture
# async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
#     """Create a database session for integration testing."""
#     async_session = async_sessionmaker(
#         db_engine,
#         class_=AsyncSession,
#         expire_on_commit=False,
#     )
#     async with async_session() as session:
#         yield session
#         await session.rollback()
