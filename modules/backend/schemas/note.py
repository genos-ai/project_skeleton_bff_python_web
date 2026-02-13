"""
Note Schemas.

Pydantic schemas for note API request/response validation.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NoteCreate(BaseModel):
    """Schema for creating a new note."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Note title",
        examples=["My First Note"],
    )
    content: str | None = Field(
        default=None,
        max_length=10000,
        description="Note content",
        examples=["This is the content of my note."],
    )


class NoteUpdate(BaseModel):
    """Schema for updating an existing note."""

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Note title",
    )
    content: str | None = Field(
        default=None,
        max_length=10000,
        description="Note content",
    )
    is_archived: bool | None = Field(
        default=None,
        description="Archive status",
    )


class NoteResponse(BaseModel):
    """Schema for note in API responses."""

    id: str = Field(description="Note unique identifier")
    title: str = Field(description="Note title")
    content: str | None = Field(description="Note content")
    is_archived: bool = Field(description="Whether the note is archived")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class NoteListResponse(BaseModel):
    """Schema for listing notes."""

    id: str
    title: str
    is_archived: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
