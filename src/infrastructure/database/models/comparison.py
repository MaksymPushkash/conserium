import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import Base, UUIDPrimaryKeyMixin


class ComparisonModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "comparisons"
    __table_args__ = (
        Index("ix_comparisons_user_created", "user_id", "created_at"),
        Index("ix_comparisons_user_collection_created", "user_id", "collection_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("collections.id", ondelete="SET NULL"), nullable=True, index=True)
    left_document_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    right_document_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    left_title: Mapped[str] = mapped_column(String(500), nullable=False)
    right_title: Mapped[str] = mapped_column(String(500), nullable=False)
    dimensions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_rows: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    source_metadata: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
