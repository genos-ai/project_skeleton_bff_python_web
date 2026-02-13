"""
Note Repository.

Data access layer for notes. Handles all database operations
for the Note model.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.models.note import Note
from modules.backend.repositories.base import BaseRepository


class NoteRepository(BaseRepository[Note]):
    """
    Repository for Note model.

    Inherits standard CRUD operations from BaseRepository
    and adds note-specific queries.
    """

    model = Note

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_all_active(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Note]:
        """
        Get all non-archived notes.

        Args:
            limit: Maximum number of notes to return
            offset: Number of notes to skip

        Returns:
            List of active (non-archived) notes
        """
        result = await self.session.execute(
            select(Note)
            .where(Note.is_archived == False)  # noqa: E712
            .order_by(Note.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_archived(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Note]:
        """
        Get all archived notes.

        Args:
            limit: Maximum number of notes to return
            offset: Number of notes to skip

        Returns:
            List of archived notes
        """
        result = await self.session.execute(
            select(Note)
            .where(Note.is_archived == True)  # noqa: E712
            .order_by(Note.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def search_by_title(
        self,
        query: str,
        limit: int = 50,
    ) -> list[Note]:
        """
        Search notes by title (case-insensitive).

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of notes matching the query
        """
        result = await self.session.execute(
            select(Note)
            .where(Note.title.ilike(f"%{query}%"))
            .where(Note.is_archived == False)  # noqa: E712
            .order_by(Note.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def archive(self, id: str) -> Note:
        """
        Archive a note.

        Args:
            id: Note ID to archive

        Returns:
            Updated note

        Raises:
            NotFoundError: If note not found
        """
        return await self.update(id, is_archived=True)

    async def unarchive(self, id: str) -> Note:
        """
        Unarchive a note.

        Args:
            id: Note ID to unarchive

        Returns:
            Updated note

        Raises:
            NotFoundError: If note not found
        """
        return await self.update(id, is_archived=False)

    async def count_active(self) -> int:
        """Get count of active (non-archived) notes."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Note)
            .where(Note.is_archived == False)  # noqa: E712
        )
        return result.scalar_one()
