"""
Base Repository.

Base class for all repositories with common CRUD operations.
"""

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.exceptions import NotFoundError
from modules.backend.core.logging import get_logger
from modules.backend.models.base import Base

logger = get_logger(__name__)

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Base repository with common CRUD operations.

    Subclasses should set the model class:

        class UserRepository(BaseRepository[User]):
            model = User
    """

    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id: str | UUID) -> ModelType:
        """
        Get a single record by ID.

        Raises:
            NotFoundError: If record not found
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == str(id))
        )
        instance = result.scalar_one_or_none()

        if instance is None:
            raise NotFoundError(f"{self.model.__name__} not found")

        return instance

    async def get_by_id_or_none(self, id: str | UUID) -> ModelType | None:
        """Get a single record by ID, returning None if not found."""
        result = await self.session.execute(
            select(self.model).where(self.model.id == str(id))
        )
        return result.scalar_one_or_none()

    async def get_all(self, limit: int = 50, offset: int = 0) -> list[ModelType]:
        """Get all records with pagination."""
        result = await self.session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> ModelType:
        """Create a new record."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: str | UUID, **kwargs: Any) -> ModelType:
        """
        Update an existing record.

        Raises:
            NotFoundError: If record not found
        """
        instance = await self.get_by_id(id)

        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)

        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, id: str | UUID) -> None:
        """
        Delete a record by ID.

        Raises:
            NotFoundError: If record not found
        """
        instance = await self.get_by_id(id)
        await self.session.delete(instance)
        await self.session.flush()

    async def exists(self, id: str | UUID) -> bool:
        """Check if a record exists by ID."""
        result = await self.session.execute(
            select(self.model.id).where(self.model.id == str(id))
        )
        return result.scalar_one_or_none() is not None
