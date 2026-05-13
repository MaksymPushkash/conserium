import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class NoteVersionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "note_versions"
    __table_args__ = (
        Index("ix_note_versions_note_created", "note_id", "created_at"),
        Index("ix_note_versions_user_note", "user_id", "note_id"),
    )

    note_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
