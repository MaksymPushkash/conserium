from __future__ import annotations

import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WorkspaceModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_workspace_user_name"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner = relationship("UserModel")


class WorkspaceMemberModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "email", name="uq_workspace_member_email"),
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member_user"),
        Index("ix_workspace_members_workspace_role", "workspace_id", "role"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    workspace = relationship("WorkspaceModel")
    user = relationship("UserModel", foreign_keys=[user_id])
    invited_by = relationship("UserModel", foreign_keys=[invited_by_user_id])


class WorkspaceAuditEventModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspace_audit_events"
    __table_args__ = (Index("ix_workspace_audit_workspace_created", "workspace_id", "created_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    event_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)

    workspace = relationship("WorkspaceModel")
    actor = relationship("UserModel")


class CollectionMemberModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "collection_members"
    __table_args__ = (
        UniqueConstraint("collection_id", "email", name="uq_collection_member_email"),
        UniqueConstraint("collection_id", "user_id", name="uq_collection_member_user"),
        Index("ix_collection_members_collection_role", "collection_id", "role"),
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    collection = relationship("CollectionModel")
    user = relationship("UserModel", foreign_keys=[user_id])
    invited_by = relationship("UserModel", foreign_keys=[invited_by_user_id])


class CollectionAuditEventModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "collection_audit_events"
    __table_args__ = (Index("ix_collection_audit_collection_created", "collection_id", "created_at"),)

    collection_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    event_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)

    collection = relationship("CollectionModel")
    actor = relationship("UserModel")
