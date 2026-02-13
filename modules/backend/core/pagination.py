"""
Pagination Utilities.

Standardized pagination for list endpoints with offset-based
and cursor-based pagination support.
"""

import base64
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

from modules.backend.schemas.base import PaginatedResponse, PaginationInfo, ResponseMetadata

T = TypeVar("T")


# =============================================================================
# Pagination Parameters
# =============================================================================


@dataclass
class PaginationParams:
    """
    Pagination parameters extracted from query string.

    Supports both offset-based and cursor-based pagination.
    """

    limit: int
    offset: int
    cursor: str | None

    @property
    def is_cursor_based(self) -> bool:
        """Check if using cursor-based pagination."""
        return self.cursor is not None


def get_pagination_params(
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of items to return",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of items to skip (offset-based pagination)",
    ),
    cursor: str | None = Query(
        default=None,
        description="Pagination cursor (cursor-based pagination)",
    ),
) -> PaginationParams:
    """
    FastAPI dependency for pagination parameters.

    Usage:
        @router.get("/items")
        async def list_items(
            pagination: PaginationParams = Depends(get_pagination_params),
        ):
            ...
    """
    return PaginationParams(limit=limit, offset=offset, cursor=cursor)


# =============================================================================
# Cursor Encoding/Decoding
# =============================================================================


def encode_cursor(value: str | int) -> str:
    """
    Encode a value as a pagination cursor.

    Args:
        value: The value to encode (typically an ID or timestamp)

    Returns:
        Base64-encoded cursor string
    """
    return base64.urlsafe_b64encode(str(value).encode()).decode()


def decode_cursor(cursor: str) -> str:
    """
    Decode a pagination cursor.

    Args:
        cursor: Base64-encoded cursor string

    Returns:
        Decoded cursor value

    Raises:
        ValueError: If cursor is invalid
    """
    try:
        return base64.urlsafe_b64decode(cursor.encode()).decode()
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {cursor}") from exc


# =============================================================================
# Paginated Result Builder
# =============================================================================


@dataclass
class PagedResult(Generic[T]):
    """
    Result container for paginated queries.

    Contains the items and pagination metadata needed to build
    a PaginatedResponse.
    """

    items: list[T]
    total: int | None
    limit: int
    offset: int
    has_more: bool
    next_cursor: str | None = None


def create_paginated_response(
    items: list[Any],
    item_schema: type[BaseModel],
    total: int | None = None,
    limit: int = 20,
    offset: int = 0,
    cursor: str | None = None,
    next_cursor: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """
    Create a standardized paginated response.

    Args:
        items: List of items (model instances or dicts)
        item_schema: Pydantic schema to validate items
        total: Total count of items (optional)
        limit: Page size limit
        offset: Current offset
        cursor: Current cursor (if cursor-based)
        next_cursor: Cursor for next page (if cursor-based)
        request_id: Request ID for metadata

    Returns:
        Dict matching PaginatedResponse structure

    Usage:
        return create_paginated_response(
            items=notes,
            item_schema=NoteListResponse,
            total=100,
            limit=20,
            offset=0,
        )
    """
    # Determine if there are more items
    has_more = False
    if total is not None:
        has_more = (offset + len(items)) < total
    elif next_cursor is not None:
        has_more = True

    # Validate items through schema
    validated_items = [
        item_schema.model_validate(item).model_dump(mode="json")
        for item in items
    ]

    # Build pagination info
    pagination = PaginationInfo(
        total=total,
        limit=limit,
        cursor=cursor,
        next_cursor=next_cursor,
        has_more=has_more,
    )

    # Build metadata
    metadata = ResponseMetadata(request_id=request_id)

    # Build response
    response = PaginatedResponse(
        data=validated_items,
        pagination=pagination,
        metadata=metadata,
    )

    return response.model_dump(mode="json")


# =============================================================================
# Pagination Helper for Repositories
# =============================================================================


async def paginate_query(
    query_func,
    params: PaginationParams,
    count_func=None,
) -> PagedResult:
    """
    Execute a paginated query.

    Args:
        query_func: Async function that takes (limit, offset) and returns items
        params: Pagination parameters
        count_func: Optional async function that returns total count

    Returns:
        PagedResult with items and pagination metadata

    Usage:
        result = await paginate_query(
            query_func=lambda limit, offset: repo.get_all(limit=limit, offset=offset),
            params=pagination,
            count_func=repo.count,
        )
    """
    # Fetch one extra item to determine if there are more
    items = await query_func(params.limit + 1, params.offset)

    # Check if there are more items
    has_more = len(items) > params.limit
    if has_more:
        items = items[:params.limit]

    # Get total count if function provided
    total = None
    if count_func is not None:
        total = await count_func()

    # Generate next cursor if using cursor-based pagination
    next_cursor = None
    if has_more and items:
        # Use the last item's ID as cursor
        last_item = items[-1]
        if hasattr(last_item, "id"):
            next_cursor = encode_cursor(last_item.id)

    return PagedResult(
        items=items,
        total=total,
        limit=params.limit,
        offset=params.offset,
        has_more=has_more,
        next_cursor=next_cursor,
    )
