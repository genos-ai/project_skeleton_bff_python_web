"""
Database Configuration.

SQLAlchemy async engine and session management.
Uses lazy initialization to prevent import-time failures when .env is not configured.
"""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

# Module-level state for lazy initialization
_engine: Any = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def _create_engine() -> Any:
    """Create async SQLAlchemy engine."""
    from modules.backend.core.config import get_app_config, get_settings

    settings = get_settings()
    db_config = get_app_config().database

    engine = create_async_engine(
        settings.database_url,
        pool_size=db_config.get("pool_size"),
        max_overflow=db_config.get("max_overflow"),
        pool_timeout=db_config.get("pool_timeout"),
        pool_recycle=db_config.get("pool_recycle"),
        echo=db_config.get("echo"),
    )
    logger.debug("Database engine created", extra={"url": settings.db_host})
    return engine


def get_engine() -> Any:
    """
    Get the database engine, creating it on first use.

    Returns:
        SQLAlchemy async engine instance

    Raises:
        RuntimeError: If database configuration is invalid
    """
    global _engine
    if _engine is None:
        _engine = _create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Get the session factory, creating it on first use.

    Returns:
        SQLAlchemy async session factory
    """
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session.

    Usage in endpoints:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
