"""
Note Service.

Business logic layer for notes. Orchestrates repositories,
handles validation, and implements business rules.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.models.note import Note
from modules.backend.repositories.note import NoteRepository
from modules.backend.schemas.note import NoteCreate, NoteUpdate
from modules.backend.services.base import BaseService


class NoteService(BaseService):
    """
    Service for note business logic.

    Handles note creation, updates, and retrieval with
    proper validation and error handling.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repo = NoteRepository(session)

    async def create_note(self, data: NoteCreate) -> Note:
        """
        Create a new note.

        Args:
            data: Note creation data

        Returns:
            Created note
        """
        self._log_operation("Creating note", title=data.title)

        note = await self._execute_db_operation(
            "create_note",
            self.repo.create(
                title=data.title,
                content=data.content,
            ),
        )

        self._log_debug("Note created", note_id=note.id)
        return note

    async def get_note(self, note_id: str) -> Note:
        """
        Get a note by ID.

        Args:
            note_id: Note ID

        Returns:
            Note if found

        Raises:
            NotFoundError: If note not found
        """
        return await self.repo.get_by_id(note_id)

    async def list_notes(
        self,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Note]:
        """
        List notes with optional filtering.

        Args:
            include_archived: Whether to include archived notes
            limit: Maximum number of notes
            offset: Number to skip for pagination

        Returns:
            List of notes
        """
        if include_archived:
            return await self.repo.get_all(limit=limit, offset=offset)
        return await self.repo.get_all_active(limit=limit, offset=offset)

    async def list_notes_paginated(
        self,
        include_archived: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Note], int]:
        """
        List notes with total count for pagination.

        Args:
            include_archived: Whether to include archived notes
            limit: Maximum number of notes
            offset: Number to skip for pagination

        Returns:
            Tuple of (notes list, total count)
        """
        if include_archived:
            notes = await self.repo.get_all(limit=limit, offset=offset)
            total = await self.repo.count()
        else:
            notes = await self.repo.get_all_active(limit=limit, offset=offset)
            total = await self.repo.count_active()

        return notes, total

    async def update_note(self, note_id: str, data: NoteUpdate) -> Note:
        """
        Update an existing note.

        Args:
            note_id: Note ID to update
            data: Update data (only non-None fields are updated)

        Returns:
            Updated note

        Raises:
            NotFoundError: If note not found
        """
        # Build update kwargs from non-None fields
        update_data = data.model_dump(exclude_unset=True)

        if not update_data:
            # No fields to update, just return the existing note
            return await self.repo.get_by_id(note_id)

        self._log_operation(
            "Updating note",
            note_id=note_id,
            fields=list(update_data.keys()),
        )

        note = await self._execute_db_operation(
            "update_note",
            self.repo.update(note_id, **update_data),
        )

        return note

    async def delete_note(self, note_id: str) -> None:
        """
        Delete a note.

        Args:
            note_id: Note ID to delete

        Raises:
            NotFoundError: If note not found
        """
        self._log_operation("Deleting note", note_id=note_id)

        await self._execute_db_operation(
            "delete_note",
            self.repo.delete(note_id),
        )

    async def archive_note(self, note_id: str) -> Note:
        """
        Archive a note.

        Args:
            note_id: Note ID to archive

        Returns:
            Archived note

        Raises:
            NotFoundError: If note not found
        """
        self._log_operation("Archiving note", note_id=note_id)
        return await self.repo.archive(note_id)

    async def unarchive_note(self, note_id: str) -> Note:
        """
        Unarchive a note.

        Args:
            note_id: Note ID to unarchive

        Returns:
            Unarchived note

        Raises:
            NotFoundError: If note not found
        """
        self._log_operation("Unarchiving note", note_id=note_id)
        return await self.repo.unarchive(note_id)

    async def search_notes(self, query: str, limit: int = 50) -> list[Note]:
        """
        Search notes by title.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching notes
        """
        self._log_debug("Searching notes", query=query)
        return await self.repo.search_by_title(query, limit=limit)
