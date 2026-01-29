"""
Base Schemas.

Standard API response schemas following architecture standards.
"""

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return current UTC time as timezone-naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


DataT = TypeVar("DataT")


class ResponseMetadata(BaseModel):
    """Metadata included in all API responses."""

    timestamp: datetime = Field(default_factory=utc_now)
    request_id: str | None = None


class ErrorDetail(BaseModel):
    """Error detail structure."""

    code: str
    message: str
    details: dict[str, Any] | None = None


class ApiResponse(BaseModel, Generic[DataT]):
    """
    Standard API response envelope.

    All API responses use this structure for consistency.
    """

    success: bool = True
    data: DataT | None = None
    error: ErrorDetail | None = None
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata)

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    """Standard error response."""

    success: bool = False
    data: None = None
    error: ErrorDetail
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata)


class PaginatedResponse(BaseModel, Generic[DataT]):
    """Paginated response with cursor-based navigation."""

    success: bool = True
    data: list[DataT]
    error: None = None
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata)
    pagination: "PaginationInfo"


class PaginationInfo(BaseModel):
    """Pagination metadata."""

    total: int | None = None
    limit: int
    cursor: str | None = None
    next_cursor: str | None = None
    has_more: bool = False


# Example usage:
#
# class UserSchema(BaseModel):
#     id: str
#     email: str
#
# @router.get("/users/{user_id}", response_model=ApiResponse[UserSchema])
# async def get_user(user_id: str):
#     user = await user_service.get(user_id)
#     return ApiResponse(data=user)
