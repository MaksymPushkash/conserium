from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from src.collections.repository import CollectionRepository
from src.kit.exceptions import ResourceNotFoundException, ValidationException
from src.workspaces.repository import SharedWorkspaceRepository

if TYPE_CHECKING:
    from uuid import UUID

    from src.postgres import AsyncSession
    from src.workspaces.schemas import WorkspaceRecord

MEMBER_ROLES = {"viewer", "editor"}
WRITE_ROLES = {"editor"}


async def ensure_collection_owner(session: AsyncSession, *, user_id: UUID, collection_id: UUID) -> None:
    collection = await CollectionRepository.from_session(session).get_by_id(collection_id)
    
    if collection is None or collection.user_id != user_id:
        raise ResourceNotFoundException("collection not found")


async def ensure_workspace_visible(session: AsyncSession, *, workspace_id: UUID, user_id: UUID) -> str:
    repository = SharedWorkspaceRepository.from_session(session)
    workspace = await repository.get_workspace(workspace_id=workspace_id)
    
    if workspace is None:
        raise ResourceNotFoundException("workspace not found")
        
    if workspace.user_id == user_id:
        return "owner"
        
    member = await repository.get_workspace_member_for_user(workspace_id=workspace_id, user_id=user_id)
    
    if member is None:
        raise ResourceNotFoundException("workspace not found")
        
    return member.role


async def ensure_workspace_write_access(session: AsyncSession, *, workspace_id: UUID, user_id: UUID) -> WorkspaceRecord:
    repository = SharedWorkspaceRepository.from_session(session)
    workspace = await repository.get_workspace(workspace_id=workspace_id)
    
    if workspace is None:
        raise ResourceNotFoundException("workspace not found")
        
    if workspace.user_id == user_id:
        return workspace
        
    member = await repository.get_workspace_member_for_user(workspace_id=workspace_id, user_id=user_id)
    
    if member is None or member.role not in WRITE_ROLES:
        raise ResourceNotFoundException("workspace not found")
        
    return workspace


async def ensure_collection_visible(session: AsyncSession, *, collection_id: UUID, user_id: UUID) -> str:
    collection = await CollectionRepository.from_session(session).get_by_id(collection_id)
    
    if collection is None:
        raise ResourceNotFoundException("collection not found")
        
    if collection.user_id == user_id:
        return "owner"
        
    repository = SharedWorkspaceRepository.from_session(session)
    
    if collection.workspace_id is not None:
        workspace_member = await repository.get_workspace_member_for_user(workspace_id=collection.workspace_id, user_id=user_id)
        if workspace_member is not None:
            return workspace_member.role
            
    member = await repository.get_member_for_user(collection_id=collection_id, user_id=user_id)
    
    if member is None:
        raise ResourceNotFoundException("collection not found")
        
    return member.role


def normalize_member_role(role: str) -> Literal["viewer", "editor"]:
    normalized = role.strip().lower()
    
    if normalized not in MEMBER_ROLES:
        raise ValidationException("collection member role must be viewer or editor")
    return cast("Literal['viewer', 'editor']", normalized)
