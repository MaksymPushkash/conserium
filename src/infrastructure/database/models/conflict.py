import uuid

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentClaimModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_claims"
    __table_args__ = (
        Index("ix_document_claims_user_subject", "user_id", "subject"),
        Index("ix_document_claims_document_id", "document_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    polarity: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)


class ClaimConflictModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "claim_conflicts"
    __table_args__ = (
        Index("ix_claim_conflicts_user_collection", "user_id", "collection_id"),
        Index("ix_claim_conflicts_user_subject", "user_id", "subject"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=True)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    document_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    score: Mapped[float] = mapped_column(Float, nullable=False)
