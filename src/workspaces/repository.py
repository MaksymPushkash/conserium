from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from src.models.shared_workspace import (
    CollectionAuditEventModel,
    CollectionMemberModel,
    WorkspaceAuditEventModel,
    WorkspaceMemberModel,
    WorkspaceModel,
)
from src.workspaces.schemas import (
    CollectionAuditEventRecord,
    CollectionMemberRecord,
    WorkspaceAuditEventRecord,
    WorkspaceMemberRecord,
    WorkspaceRecord,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class SharedWorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> SharedWorkspaceRepository:
        return cls(session)

    async def create_workspace(self, *, user_id: UUID, name: str, description: str | None) -> WorkspaceRecord:
        model = WorkspaceModel(id=uuid.uuid4(), user_id=user_id, name=name.strip(), description=description)
        self._session.add(model)
        await self._session.flush()
        return _workspace_to_record(model, access_role="owner")

    async def get_workspace(self, *, workspace_id: UUID) -> WorkspaceRecord | None:
        model = await self._session.scalar(
            select(WorkspaceModel).where(WorkspaceModel.id == workspace_id, WorkspaceModel.archived_at.is_(None))
        )
        return _workspace_to_record(model, access_role="owner") if model else None

    async def update_workspace(self, *, workspace_id: UUID, name: str, description: str | None) -> WorkspaceRecord | None:
        model = await self._session.scalar(
            select(WorkspaceModel).where(WorkspaceModel.id == workspace_id, WorkspaceModel.archived_at.is_(None))
        )
        if model is None:
            return None
        model.name = name.strip()
        model.description = description
        model.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _workspace_to_record(model, access_role="owner")

    async def archive_workspace(self, *, workspace_id: UUID) -> bool:
        statement = (
            update(WorkspaceModel)
            .where(WorkspaceModel.id == workspace_id, WorkspaceModel.archived_at.is_(None))
            .values(archived_at=datetime.now(UTC), updated_at=datetime.now(UTC))
            .returning(WorkspaceModel.id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def update_workspace_owner(self, *, workspace_id: UUID, user_id: UUID) -> WorkspaceRecord | None:
        model = await self._session.scalar(select(WorkspaceModel).where(WorkspaceModel.id == workspace_id))
        if model is None:
            return None
        model.user_id = user_id
        model.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _workspace_to_record(model, access_role="owner")

    async def transfer_workspace_owner_if_current(
        self,
        *,
        workspace_id: UUID,
        current_owner_user_id: UUID,
        new_owner_user_id: UUID,
    ) -> WorkspaceRecord | None:
        now = datetime.now(UTC)
        statement = (
            update(WorkspaceModel)
            .where(
                WorkspaceModel.id == workspace_id,
                WorkspaceModel.user_id == current_owner_user_id,
            )
            .values(user_id=new_owner_user_id, updated_at=now)
            .returning(WorkspaceModel)
        )
        result = await self._session.execute(statement)
        model = result.scalar_one_or_none()
        return _workspace_to_record(model, access_role="owner") if model else None

    async def list_workspaces_for_user(self, *, user_id: UUID, limit: int = 100, offset: int = 0) -> tuple[list[WorkspaceRecord], int]:
        member_workspace_ids = select(WorkspaceMemberModel.workspace_id).where(WorkspaceMemberModel.user_id == user_id)
        condition = ((WorkspaceModel.user_id == user_id) | WorkspaceModel.id.in_(member_workspace_ids)) & WorkspaceModel.archived_at.is_(None)
        total_result = await self._session.execute(select(func.count()).select_from(WorkspaceModel).where(condition))
        result = await self._session.execute(
            select(WorkspaceModel, WorkspaceMemberModel.role)
            .outerjoin(
                WorkspaceMemberModel,
                (WorkspaceMemberModel.workspace_id == WorkspaceModel.id) & (WorkspaceMemberModel.user_id == user_id),
            )
            .where(condition)
            .order_by(WorkspaceModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = [
            _workspace_to_record(model, access_role="owner" if model.user_id == user_id else role)
            for model, role in result.all()
        ]
        return items, total_result.scalar_one()

    async def get_workspace_member(self, *, workspace_id: UUID, member_id: UUID) -> WorkspaceMemberRecord | None:
        result = await self._session.execute(
            select(WorkspaceMemberModel).where(
                WorkspaceMemberModel.workspace_id == workspace_id,
                WorkspaceMemberModel.id == member_id,
            )
        )
        model = result.scalar_one_or_none()
        return _workspace_member_to_record(model) if model else None

    async def get_workspace_member_for_user(self, *, workspace_id: UUID, user_id: UUID) -> WorkspaceMemberRecord | None:
        result = await self._session.execute(
            select(WorkspaceMemberModel).where(
                WorkspaceMemberModel.workspace_id == workspace_id,
                WorkspaceMemberModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return _workspace_member_to_record(model) if model else None

    async def list_workspace_members(self, *, workspace_id: UUID) -> list[WorkspaceMemberRecord]:
        result = await self._session.execute(
            select(WorkspaceMemberModel)
            .where(WorkspaceMemberModel.workspace_id == workspace_id)
            .order_by(WorkspaceMemberModel.created_at.asc())
        )
        return [_workspace_member_to_record(model) for model in result.scalars().all()]

    async def upsert_workspace_member(
        self,
        *,
        workspace_id: UUID,
        email: str,
        role: str,
        invited_by_user_id: UUID,
        user_id: UUID | None,
    ) -> WorkspaceMemberRecord:
        now = datetime.now(UTC)
        values = {
            "id": uuid.uuid4(),
            "workspace_id": workspace_id,
            "email": email.lower(),
            "role": role,
            "invited_by_user_id": invited_by_user_id,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        statement = (
            insert(WorkspaceMemberModel)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_workspace_member_email",
                set_={"role": role, "user_id": user_id, "updated_at": now},
            )
            .returning(WorkspaceMemberModel)
        )
        result = await self._session.execute(statement)
        return _workspace_member_to_record(result.scalar_one())

    async def update_workspace_member_role(self, *, member_id: UUID, role: str) -> WorkspaceMemberRecord | None:
        result = await self._session.execute(select(WorkspaceMemberModel).where(WorkspaceMemberModel.id == member_id))
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.role = role
        model.updated_at = datetime.now(UTC)
        return _workspace_member_to_record(model)

    async def remove_workspace_member(self, *, member_id: UUID) -> bool:
        existing = await self._session.scalar(select(WorkspaceMemberModel.id).where(WorkspaceMemberModel.id == member_id))
        if existing is None:
            return False
        await self._session.execute(delete(WorkspaceMemberModel).where(WorkspaceMemberModel.id == member_id))
        return True

    async def create_workspace_audit_event(
        self,
        *,
        workspace_id: UUID,
        actor_user_id: UUID,
        event_type: str,
        metadata: dict[str, object],
    ) -> WorkspaceAuditEventRecord:
        model = WorkspaceAuditEventModel(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            event_metadata=metadata,
        )
        self._session.add(model)
        await self._session.flush()
        return _workspace_audit_to_record(model)

    async def list_workspace_audit_events(
        self,
        *,
        workspace_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[WorkspaceAuditEventRecord], int]:
        total_result = await self._session.execute(
            select(func.count()).select_from(WorkspaceAuditEventModel).where(WorkspaceAuditEventModel.workspace_id == workspace_id)
        )
        result = await self._session.execute(
            select(WorkspaceAuditEventModel)
            .where(WorkspaceAuditEventModel.workspace_id == workspace_id)
            .order_by(WorkspaceAuditEventModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_workspace_audit_to_record(model) for model in result.scalars().all()], total_result.scalar_one()

    async def get_member(self, *, collection_id: UUID, member_id: UUID) -> CollectionMemberRecord | None:
        result = await self._session.execute(
            select(CollectionMemberModel).where(
                CollectionMemberModel.collection_id == collection_id,
                CollectionMemberModel.id == member_id,
            )
        )
        model = result.scalar_one_or_none()
        return _member_to_record(model) if model else None

    async def get_member_for_user(self, *, collection_id: UUID, user_id: UUID) -> CollectionMemberRecord | None:
        result = await self._session.execute(
            select(CollectionMemberModel).where(
                CollectionMemberModel.collection_id == collection_id,
                CollectionMemberModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return _member_to_record(model) if model else None

    async def list_members(self, *, collection_id: UUID) -> list[CollectionMemberRecord]:
        result = await self._session.execute(
            select(CollectionMemberModel)
            .where(CollectionMemberModel.collection_id == collection_id)
            .order_by(CollectionMemberModel.created_at.asc())
        )
        return [_member_to_record(model) for model in result.scalars().all()]

    async def upsert_member(
        self,
        *,
        collection_id: UUID,
        email: str,
        role: str,
        invited_by_user_id: UUID,
        user_id: UUID | None,
    ) -> CollectionMemberRecord:
        now = datetime.now(UTC)
        values = {
            "id": uuid.uuid4(),
            "collection_id": collection_id,
            "email": email.lower(),
            "role": role,
            "invited_by_user_id": invited_by_user_id,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        statement = (
            insert(CollectionMemberModel)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_collection_member_email",
                set_={"role": role, "user_id": user_id, "updated_at": now},
            )
            .returning(CollectionMemberModel)
        )
        result = await self._session.execute(statement)
        return _member_to_record(result.scalar_one())

    async def update_member_role(self, *, member_id: UUID, role: str) -> CollectionMemberRecord | None:
        result = await self._session.execute(select(CollectionMemberModel).where(CollectionMemberModel.id == member_id))
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.role = role
        model.updated_at = datetime.now(UTC)
        return _member_to_record(model)

    async def remove_member(self, *, member_id: UUID) -> bool:
        existing = await self._session.scalar(select(CollectionMemberModel.id).where(CollectionMemberModel.id == member_id))
        if existing is None:
            return False
        await self._session.execute(delete(CollectionMemberModel).where(CollectionMemberModel.id == member_id))
        return True

    async def create_audit_event(
        self,
        *,
        collection_id: UUID,
        actor_user_id: UUID,
        event_type: str,
        metadata: dict[str, object],
    ) -> CollectionAuditEventRecord:
        model = CollectionAuditEventModel(
            id=uuid.uuid4(),
            collection_id=collection_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            event_metadata=metadata,
        )
        self._session.add(model)
        await self._session.flush()
        return _audit_to_record(model)

    async def list_audit_events(
        self,
        *,
        collection_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[CollectionAuditEventRecord], int]:
        total_result = await self._session.execute(
            select(func.count()).select_from(CollectionAuditEventModel).where(CollectionAuditEventModel.collection_id == collection_id)
        )
        result = await self._session.execute(
            select(CollectionAuditEventModel)
            .where(CollectionAuditEventModel.collection_id == collection_id)
            .order_by(CollectionAuditEventModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_audit_to_record(model) for model in result.scalars().all()], total_result.scalar_one()


def _member_to_record(model: CollectionMemberModel) -> CollectionMemberRecord:
    return CollectionMemberRecord(
        id=model.id,
        collection_id=model.collection_id,
        user_id=model.user_id,
        email=model.email,
        role=model.role,
        invited_by_user_id=model.invited_by_user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _audit_to_record(model: CollectionAuditEventModel) -> CollectionAuditEventRecord:
    return CollectionAuditEventRecord(
        id=model.id,
        collection_id=model.collection_id,
        actor_user_id=model.actor_user_id,
        event_type=model.event_type,
        metadata=dict(model.event_metadata or {}),
        created_at=model.created_at,
    )


def _workspace_to_record(model: WorkspaceModel, *, access_role: str | None) -> WorkspaceRecord:
    return WorkspaceRecord(
        id=model.id,
        user_id=model.user_id,
        name=model.name,
        description=model.description,
        access_role=access_role or "viewer",
        created_at=model.created_at,
        updated_at=model.updated_at,
        archived_at=model.archived_at,
    )


def _workspace_member_to_record(model: WorkspaceMemberModel) -> WorkspaceMemberRecord:
    return WorkspaceMemberRecord(
        id=model.id,
        workspace_id=model.workspace_id,
        user_id=model.user_id,
        email=model.email,
        role=model.role,
        invite_status="active" if model.user_id else "pending",
        invited_by_user_id=model.invited_by_user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _workspace_audit_to_record(model: WorkspaceAuditEventModel) -> WorkspaceAuditEventRecord:
    return WorkspaceAuditEventRecord(
        id=model.id,
        workspace_id=model.workspace_id,
        actor_user_id=model.actor_user_id,
        event_type=model.event_type,
        metadata=dict(model.event_metadata or {}),
        created_at=model.created_at,
    )
