import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.collection import CollectionModel
    from src.models.user import UserModel


class DraftModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "drafts"
    __table_args__ = (
        Index("ix_drafts_user_updated", "user_id", "updated_at"),
        Index("ix_drafts_user_collection_updated", "user_id", "collection_id", "updated_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("collections.id", ondelete="SET NULL"), nullable=True, index=True)
    current_version_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[str] = mapped_column(String(80), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(100))
    knowledge_gap_id: Mapped[str | None] = mapped_column(String(160))
    scope_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    source_metadata: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    gaps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    user: Mapped["UserModel"] = relationship()
    collection: Mapped["CollectionModel | None"] = relationship()


class DraftVersionModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "draft_versions"
    __table_args__ = (
        Index("ix_draft_versions_draft_number", "draft_id", "version_number"),
        Index("ix_draft_versions_user_draft", "user_id", "draft_id"),
    )

    draft_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[str] = mapped_column(String(80), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("collections.id", ondelete="SET NULL"), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(100))
    knowledge_gap_id: Mapped[str | None] = mapped_column(String(160))
    scope_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    source_metadata: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    gaps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    draft: Mapped[DraftModel] = relationship()
