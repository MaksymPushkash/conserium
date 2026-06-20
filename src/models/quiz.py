import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.collection import CollectionModel
    from src.models.document import DocumentModel
    from src.models.user import UserModel


class QuizModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quizzes"
    __table_args__ = (
        Index("ix_quizzes_user_created", "user_id", "created_at"),
        Index("ix_quizzes_user_scope", "user_id", "scope_type"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("collections.id", ondelete="SET NULL"), nullable=True, index=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    questions: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    user: Mapped["UserModel"] = relationship()
    collection: Mapped["CollectionModel | None"] = relationship()
    source_document: Mapped["DocumentModel | None"] = relationship(foreign_keys=[source_document_id])


class QuizAttemptModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (
        Index("ix_quiz_attempts_user_created", "user_id", "created_at"),
        Index("ix_quiz_attempts_quiz_created", "quiz_id", "created_at"),
    )

    quiz_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    answers: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    weak_areas: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    quiz: Mapped[QuizModel] = relationship()
