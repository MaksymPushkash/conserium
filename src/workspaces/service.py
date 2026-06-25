from typing import Any, cast
from uuid import UUID

from src.kit.exceptions import ResourceNotFoundException, ValidationException
from src.postgres import AsyncSession
from src.users.repository import UserRepository
from src.workspaces.repository import SharedWorkspaceRepository
from src.workspaces.schemas import (
    WorkspaceAuditEventListResponse,
    WorkspaceAuditEventRecord,
    WorkspaceAuditEventResponse,
    WorkspaceListResponse,
    WorkspaceMemberListResponse,
    WorkspaceMemberRecord,
    WorkspaceMemberResponse,
    WorkspaceRecord,
    WorkspaceResponse,
)

MEMBER_ROLES = {"viewer", "editor"}
WRITE_ROLES = {"editor"}


class WorkspaceService:
    async def create(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        name: str,
        description: str | None,
    ) -> WorkspaceResponse:
        repository = SharedWorkspaceRepository.from_session(session)
        name = name.strip()
        if not name:
            raise ValidationException("workspace name required")
        workspace = await repository.create_workspace(
            user_id=user_id,
            name=name,
            description=description.strip() if description else None,
        )
        await repository.create_workspace_audit_event(
            workspace_id=workspace.id,
            actor_user_id=user_id,
            event_type="workspace_created",
            metadata={"name": workspace.name},
        )
        await session.flush()
        return to_workspace_response(workspace)

    async def list(self, session: AsyncSession, *, user_id: UUID, limit: int, offset: int) -> WorkspaceListResponse:
        repository = SharedWorkspaceRepository.from_session(session)
        items, total = await repository.list_workspaces_for_user(user_id=user_id, limit=limit, offset=offset)
        return WorkspaceListResponse(
            items=[to_workspace_response(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def update(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        actor_user_id: UUID,
        name: str,
        description: str | None,
    ) -> WorkspaceResponse:
        repository = SharedWorkspaceRepository.from_session(session)
        name = name.strip()
        if not name:
            raise ValidationException("workspace name required")
        existing = await ensure_workspace_owner(repository, workspace_id=workspace_id, user_id=actor_user_id)
        updated = await repository.update_workspace(
            workspace_id=workspace_id,
            name=name,
            description=description.strip() if description else None,
        )
        if updated is None:
            raise ResourceNotFoundException("workspace not found")
        await repository.create_workspace_audit_event(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            event_type="workspace_updated",
            metadata={"previous_name": existing.name, "name": updated.name},
        )
        await session.flush()
        return to_workspace_response(updated)

    async def delete(self, session: AsyncSession, *, workspace_id: UUID, actor_user_id: UUID) -> None:
        repository = SharedWorkspaceRepository.from_session(session)
        workspace = await ensure_workspace_owner(repository, workspace_id=workspace_id, user_id=actor_user_id)
        archived = await repository.archive_workspace(workspace_id=workspace_id)
        if not archived:
            raise ResourceNotFoundException("workspace not found")
        await repository.create_workspace_audit_event(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            event_type="workspace_archived",
            metadata={"name": workspace.name},
        )
        await session.flush()

    async def list_members(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        user_id: UUID,
    ) -> WorkspaceMemberListResponse:
        repository = SharedWorkspaceRepository.from_session(session)
        await ensure_workspace_visible(repository, workspace_id=workspace_id, user_id=user_id)
        members = await repository.list_workspace_members(workspace_id=workspace_id)
        return WorkspaceMemberListResponse(items=[to_workspace_member_response(member) for member in members])

    async def invite_member(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        actor_user_id: UUID,
        email: str,
        role: str,
    ) -> WorkspaceMemberResponse:
        repository = SharedWorkspaceRepository.from_session(session)
        user_repository = UserRepository.from_session(session)
        role = normalize_member_role(role)
        email = email.strip().lower()
        if "@" not in email:
            raise ValidationException("valid member email required")
        await ensure_workspace_owner(repository, workspace_id=workspace_id, user_id=actor_user_id)
        user = await user_repository.get_by_email(email)
        if user is not None and user.id == actor_user_id:
            raise ValidationException("owner is already a workspace member")
        member = await repository.upsert_workspace_member(
            workspace_id=workspace_id,
            email=email,
            role=role,
            invited_by_user_id=actor_user_id,
            user_id=user.id if user else None,
        )
        await repository.create_workspace_audit_event(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            event_type="member_invited",
            metadata={"email": email, "role": role},
        )
        await session.flush()
        return to_workspace_member_response(member)

    async def update_member_role(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        member_id: UUID,
        actor_user_id: UUID,
        role: str,
    ) -> WorkspaceMemberResponse:
        repository = SharedWorkspaceRepository.from_session(session)
        role = normalize_member_role(role)
        await ensure_workspace_owner(repository, workspace_id=workspace_id, user_id=actor_user_id)
        existing = await repository.get_workspace_member(workspace_id=workspace_id, member_id=member_id)
        if existing is None:
            raise ResourceNotFoundException("workspace member not found")
        member = await repository.update_workspace_member_role(member_id=member_id, role=role)
        if member is None:
            raise ResourceNotFoundException("workspace member not found")
        await repository.create_workspace_audit_event(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            event_type="member_role_updated",
            metadata={"email": existing.email, "previous_role": existing.role, "role": role},
        )
        await session.flush()
        return to_workspace_member_response(member)

    async def transfer_ownership(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        actor_user_id: UUID,
        member_id: UUID,
    ) -> WorkspaceResponse:
        repository = SharedWorkspaceRepository.from_session(session)
        user_repository = UserRepository.from_session(session)
        workspace = await ensure_workspace_owner(repository, workspace_id=workspace_id, user_id=actor_user_id)
        target = await repository.get_workspace_member(workspace_id=workspace_id, member_id=member_id)
        if target is None:
            raise ResourceNotFoundException("workspace member not found")
        if target.user_id is None:
            raise ValidationException("workspace ownership can only transfer to an active member")
        if target.user_id == actor_user_id:
            raise ValidationException("workspace owner is already assigned")
        actor = await user_repository.get_by_id(actor_user_id)
        updated = await repository.transfer_workspace_owner_if_current(
            workspace_id=workspace_id,
            current_owner_user_id=actor_user_id,
            new_owner_user_id=target.user_id,
        )
        if updated is None:
            raise ValidationException("workspace ownership changed; reload before transferring ownership")
        await repository.remove_workspace_member(member_id=target.id)
        if actor is not None:
            await repository.upsert_workspace_member(
                workspace_id=workspace_id,
                email=actor.email,
                role="editor",
                invited_by_user_id=target.user_id,
                user_id=actor_user_id,
            )
        await repository.create_workspace_audit_event(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            event_type="workspace_owner_transferred",
            metadata={
                "previous_owner_id": str(workspace.user_id),
                "new_owner_id": str(target.user_id),
                "new_owner_email": target.email,
            },
        )
        await session.flush()
        return to_workspace_response(updated)

    async def remove_member(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        member_id: UUID,
        actor_user_id: UUID,
    ) -> None:
        repository = SharedWorkspaceRepository.from_session(session)
        await ensure_workspace_owner(repository, workspace_id=workspace_id, user_id=actor_user_id)
        existing = await repository.get_workspace_member(workspace_id=workspace_id, member_id=member_id)
        if existing is None:
            raise ResourceNotFoundException("workspace member not found")
        await repository.remove_workspace_member(member_id=member_id)
        await repository.create_workspace_audit_event(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            event_type="member_removed",
            metadata={"email": existing.email, "role": existing.role},
        )
        await session.flush()

    async def list_audit_events(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> WorkspaceAuditEventListResponse:
        repository = SharedWorkspaceRepository.from_session(session)
        await ensure_workspace_visible(repository, workspace_id=workspace_id, user_id=user_id)
        events, total = await repository.list_workspace_audit_events(
            workspace_id=workspace_id,
            limit=limit,
            offset=offset,
        )
        return WorkspaceAuditEventListResponse(
            items=[to_workspace_audit_event_response(event) for event in events],
            total=total,
            limit=limit,
            offset=offset,
        )


async def ensure_workspace_owner(
    accessor: Any,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> WorkspaceRecord:
    repository = _shared_workspace_repo(accessor)
    workspace = cast("WorkspaceRecord | None", await repository.get_workspace(workspace_id=workspace_id))
    if workspace is None or workspace.user_id != user_id:
        raise ResourceNotFoundException("workspace not found")
    return workspace


async def ensure_workspace_visible(
    accessor: Any,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> str:
    repository = _shared_workspace_repo(accessor)
    workspace = cast("WorkspaceRecord | None", await repository.get_workspace(workspace_id=workspace_id))
    if workspace is None:
        raise ResourceNotFoundException("workspace not found")
    if workspace.user_id == user_id:
        return "owner"
    member = await repository.get_workspace_member_for_user(workspace_id=workspace_id, user_id=user_id)
    if member is None:
        raise ResourceNotFoundException("workspace not found")
    return cast("str", member.role)


async def ensure_workspace_write_access(accessor: Any, *, workspace_id: UUID, user_id: UUID) -> WorkspaceRecord:
    repository = _shared_workspace_repo(accessor)
    workspace = cast("WorkspaceRecord | None", await repository.get_workspace(workspace_id=workspace_id))
    if workspace is None:
        raise ResourceNotFoundException("workspace not found")
    if workspace.user_id == user_id:
        return workspace
    member = await repository.get_workspace_member_for_user(workspace_id=workspace_id, user_id=user_id)
    if member is None or member.role not in WRITE_ROLES:
        raise ResourceNotFoundException("workspace not found")
    return workspace


async def ensure_collection_owner(accessor: Any, *, collection_id: UUID, user_id: UUID) -> None:
    collection = await _collection_repo(accessor).get_by_id(collection_id)
    if collection is None or collection.user_id != user_id:
        raise ResourceNotFoundException("collection not found")


async def ensure_collection_visible(accessor: Any, *, collection_id: UUID, user_id: UUID) -> str:
    collection = await _collection_repo(accessor).get_by_id(collection_id)
    if collection is None:
        raise ResourceNotFoundException("collection not found")
    if collection.user_id == user_id:
        return "owner"
    try:
        repository = _shared_workspace_repo(accessor)
    except AttributeError as exc:
        raise ResourceNotFoundException("collection not found") from exc
    workspace_id = getattr(collection, "workspace_id", None)
    if workspace_id is not None:
        workspace_member = await repository.get_workspace_member_for_user(workspace_id=workspace_id, user_id=user_id)
        if workspace_member is not None:
            return cast("str", workspace_member.role)
    member = await repository.get_member_for_user(collection_id=collection_id, user_id=user_id)
    if member is None:
        raise ResourceNotFoundException("collection not found")
    return cast("str", member.role)


async def ensure_collection_write_access(accessor: Any, *, collection_id: UUID, user_id: UUID) -> str:
    role = await ensure_collection_visible(accessor, collection_id=collection_id, user_id=user_id)
    if role != "owner" and role not in WRITE_ROLES:
        raise ResourceNotFoundException("collection not found")
    return role


def _shared_workspace_repo(accessor: Any) -> Any:
    if hasattr(accessor, "shared_workspace_repo"):
        return accessor.shared_workspace_repo
    if hasattr(accessor, "get_workspace"):
        return accessor
    raise AttributeError("shared workspace repository unavailable")


def _collection_repo(accessor: Any) -> Any:
    return accessor.collection_repo


def normalize_member_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in MEMBER_ROLES:
        raise ValidationException("collection member role must be viewer or editor")
    return normalized


def to_workspace_response(dto: WorkspaceRecord) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=dto.id,
        user_id=dto.user_id,
        name=dto.name,
        description=dto.description,
        access_role=dto.access_role,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
        archived_at=dto.archived_at,
    )


def to_workspace_member_response(dto: WorkspaceMemberRecord) -> WorkspaceMemberResponse:
    return WorkspaceMemberResponse(
        id=dto.id,
        workspace_id=dto.workspace_id,
        user_id=dto.user_id,
        email=dto.email,
        role=dto.role,
        invite_status=dto.invite_status,
        invited_by_user_id=dto.invited_by_user_id,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_workspace_audit_event_response(dto: WorkspaceAuditEventRecord) -> WorkspaceAuditEventResponse:
    return WorkspaceAuditEventResponse(
        id=dto.id,
        workspace_id=dto.workspace_id,
        actor_user_id=dto.actor_user_id,
        event_type=dto.event_type,
        metadata=dto.metadata,
        created_at=dto.created_at,
    )


workspaces = WorkspaceService()

__all__ = [
    "WorkspaceService",
    "ensure_collection_visible",
    "ensure_collection_write_access",
    "ensure_workspace_visible",
    "ensure_workspace_write_access",
    "normalize_member_role",
    "workspaces",
]
