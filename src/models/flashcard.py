import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.collection import CollectionModel
    from src.models.document import DocumentModel
    from src.models.user import UserModel


class FlashcardModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "flashcards"
    __table_args__ = (
        Index("ix_flashcards_user_due", "user_id", "due_at"),
        Index("ix_flashcards_user_document", "user_id", "source_document_id"),
        Index("ix_flashcards_user_scope", "user_id", "scope_type"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("collections.id", ondelete="SET NULL"), nullable=True, index=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(120))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    citation_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ease_factor: Mapped[float] = mapped_column(Float, nullable=False, default=2.5)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    user: Mapped["UserModel"] = relationship()
    collection: Mapped["CollectionModel | None"] = relationship()
    source_document: Mapped["DocumentModel | None"] = relationship(foreign_keys=[source_document_id])


class FlashcardReviewModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "flashcard_reviews"
    __table_args__ = (
        Index("ix_flashcard_reviews_user_reviewed", "user_id", "reviewed_at"),
        Index("ix_flashcard_reviews_flashcard_reviewed", "flashcard_id", "reviewed_at"),
    )

    flashcard_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("flashcards.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    grade: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    next_interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_ease_factor: Mapped[float] = mapped_column(Float, nullable=False)
    next_ease_factor: Mapped[float] = mapped_column(Float, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    flashcard: Mapped[FlashcardModel] = relationship()
