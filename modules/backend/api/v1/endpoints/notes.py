"""
Notes API Endpoints.

REST API endpoints for note management.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query

from modules.backend.core.dependencies import DbSession, RequestId
from modules.backend.core.pagination import (
    PaginationParams,
    create_paginated_response,
    get_pagination_params,
)
from modules.backend.schemas.base import ApiResponse
from modules.backend.schemas.note import (
    NoteCreate,
    NoteListResponse,
    NoteResponse,
    NoteUpdate,
)
from modules.backend.services.note import NoteService

router = APIRouter()


@router.post(
    "",
    response_model=ApiResponse[NoteResponse],
    status_code=201,
    summary="Create a note",
    description="Create a new note with title and optional content.",
)
async def create_note(
    data: NoteCreate,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[NoteResponse]:
    """Create a new note."""
    service = NoteService(db)
    note = await service.create_note(data)
    return ApiResponse(data=NoteResponse.model_validate(note))


@router.get(
    "",
    summary="List notes (paginated)",
    description="Get a paginated list of notes with total count and pagination info.",
)
async def list_notes(
    db: DbSession,
    request_id: RequestId,
    pagination: PaginationParams = Depends(get_pagination_params),
    include_archived: bool = Query(
        default=False,
        description="Include archived notes",
    ),
) -> dict[str, Any]:
    """List notes with full pagination support."""
    service = NoteService(db)

    # Get notes and total count
    notes, total = await service.list_notes_paginated(
        include_archived=include_archived,
        limit=pagination.limit,
        offset=pagination.offset,
    )

    return create_paginated_response(
        items=notes,
        item_schema=NoteListResponse,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        request_id=request_id,
    )


@router.get(
    "/search",
    response_model=ApiResponse[list[NoteListResponse]],
    summary="Search notes",
    description="Search notes by title.",
)
async def search_notes(
    db: DbSession,
    request_id: RequestId,
    q: str = Query(
        ...,
        min_length=1,
        max_length=100,
        description="Search query",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
        description="Maximum number of results",
    ),
) -> ApiResponse[list[NoteListResponse]]:
    """Search notes by title."""
    service = NoteService(db)
    notes = await service.search_notes(q, limit=limit)
    return ApiResponse(
        data=[NoteListResponse.model_validate(note) for note in notes]
    )


@router.get(
    "/{note_id}",
    response_model=ApiResponse[NoteResponse],
    summary="Get a note",
    description="Get a single note by ID.",
)
async def get_note(
    note_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[NoteResponse]:
    """Get a note by ID."""
    service = NoteService(db)
    note = await service.get_note(note_id)
    return ApiResponse(data=NoteResponse.model_validate(note))


@router.patch(
    "/{note_id}",
    response_model=ApiResponse[NoteResponse],
    summary="Update a note",
    description="Update an existing note. Only provided fields are updated.",
)
async def update_note(
    note_id: str,
    data: NoteUpdate,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[NoteResponse]:
    """Update a note."""
    service = NoteService(db)
    note = await service.update_note(note_id, data)
    return ApiResponse(data=NoteResponse.model_validate(note))


@router.delete(
    "/{note_id}",
    status_code=204,
    summary="Delete a note",
    description="Permanently delete a note.",
)
async def delete_note(
    note_id: str,
    db: DbSession,
    request_id: RequestId,
) -> None:
    """Delete a note."""
    service = NoteService(db)
    await service.delete_note(note_id)


@router.post(
    "/{note_id}/archive",
    response_model=ApiResponse[NoteResponse],
    summary="Archive a note",
    description="Archive a note (soft delete).",
)
async def archive_note(
    note_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[NoteResponse]:
    """Archive a note."""
    service = NoteService(db)
    note = await service.archive_note(note_id)
    return ApiResponse(data=NoteResponse.model_validate(note))


@router.post(
    "/{note_id}/unarchive",
    response_model=ApiResponse[NoteResponse],
    summary="Unarchive a note",
    description="Restore an archived note.",
)
async def unarchive_note(
    note_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[NoteResponse]:
    """Unarchive a note."""
    service = NoteService(db)
    note = await service.unarchive_note(note_id)
    return ApiResponse(data=NoteResponse.model_validate(note))
