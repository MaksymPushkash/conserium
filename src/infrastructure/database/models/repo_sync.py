import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.infrastructure.database.models.collection import CollectionModel
    from src.infrastructure.database.models.document import DocumentModel
    from src.infrastructure.database.models.user import UserModel


class RepoSyncModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "repo_syncs"
    __table_args__ = (
        UniqueConstraint("user_id", "owner", "repo", "branch", name="uq_repo_sync_user_repo_branch"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="github")
    owner: Mapped[str] = mapped_column(String(120), nullable=False)
    repo: Mapped[str] = mapped_column(String(120), nullable=False)
    branch: Mapped[str] = mapped_column(String(120), nullable=False, default="main")
    include_paths: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    exclude_paths: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="idle")
    last_error: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["UserModel"] = relationship()
    collection: Mapped["CollectionModel"] = relationship()


class RepoSyncItemModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "repo_sync_items"
    __table_args__ = (
        UniqueConstraint("repo_sync_id", "path", name="uq_repo_sync_item_path"),
    )

    repo_sync_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("repo_syncs.id", ondelete="CASCADE"), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    sha: Mapped[str] = mapped_column(String(120), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    repo_sync: Mapped["RepoSyncModel"] = relationship()
    document: Mapped["DocumentModel"] = relationship()


class RepoSyncOutboxModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "repo_sync_outbox"
    __table_args__ = (
        Index(
            "uq_repo_sync_outbox_active_task",
            "repo_sync_id",
            "document_id",
            "task_name",
            unique=True,
            postgresql_where=text("status != 'dispatched'"),
        ),
    )

    repo_sync_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("repo_syncs.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    task_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repo_sync: Mapped["RepoSyncModel"] = relationship()
    document: Mapped["DocumentModel"] = relationship()
