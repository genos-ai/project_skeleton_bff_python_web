"""
Database Configuration.

SQLAlchemy async engine and session management.
"""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.backend.core.config import get_app_config, get_settings


def create_engine() -> Any:
    """Create async SQLAlchemy engine."""
    settings = get_settings()
    db_config = get_app_config().database

    engine = create_async_engine(
        settings.database_url,
        pool_size=db_config.get("pool_size", 5),
        max_overflow=db_config.get("max_overflow", 10),
        pool_timeout=db_config.get("pool_timeout", 30),
        pool_recycle=db_config.get("pool_recycle", 1800),
        echo=db_config.get("echo", False),
    )
    return engine


# Create engine instance
engine = create_engine()

# Create session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session.

    Usage in endpoints:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
