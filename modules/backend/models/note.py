"""
Note Model.

Database model for notes - a simple example domain entity.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from modules.backend.models.base import Base, TimestampMixin, UUIDMixin


class Note(UUIDMixin, TimestampMixin, Base):
    """
    Note database model.

    Represents a simple note with a title and content.
    Demonstrates the standard model pattern with UUID primary key
    and automatic timestamps.
    """

    __tablename__ = "notes"

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    is_archived: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Note(id={self.id}, title={self.title!r})>"
