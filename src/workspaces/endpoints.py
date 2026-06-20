from uuid import UUID

from fastapi import Depends, Query, Response, status

from src.auth.auth import CurrentUser
from src.postgres import AsyncReadSession, AsyncSession, get_db_read_session, get_db_session
from src.routing import APIRouter
from src.workspaces.schemas import (
    WorkspaceAuditEventListResponse,
    WorkspaceListResponse,
    WorkspaceMemberListResponse,
    WorkspaceMemberRequest,
    WorkspaceMemberResponse,
    WorkspaceMemberRoleRequest,
    WorkspaceOwnershipTransferRequest,
    WorkspaceRequest,
    WorkspaceResponse,
)
from src.workspaces.service import WorkspaceService, workspaces

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def get_workspace_service() -> WorkspaceService:
    return workspaces


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    return await service.create(session, user_id=current_user.id, name=body.name, description=body.description)


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: WorkspaceService = Depends(get_workspace_service),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> WorkspaceListResponse:
    return await service.list(session, user_id=current_user.id, limit=limit, offset=offset)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    body: WorkspaceRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    return await service.update(
        session,
        workspace_id=workspace_id,
        actor_user_id=current_user.id,
        name=body.name,
        description=body.description,
    )


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: WorkspaceService = Depends(get_workspace_service),
) -> Response:
    await service.delete(session, workspace_id=workspace_id, actor_user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{workspace_id}/members", response_model=WorkspaceMemberListResponse)
async def list_workspace_members(
    workspace_id: UUID,
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceMemberListResponse:
    return await service.list_members(session, workspace_id=workspace_id, user_id=current_user.id)


@router.post("/{workspace_id}/members", response_model=WorkspaceMemberResponse, status_code=status.HTTP_201_CREATED)
async def invite_workspace_member(
    workspace_id: UUID,
    body: WorkspaceMemberRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceMemberResponse:
    return await service.invite_member(
        session,
        workspace_id=workspace_id,
        actor_user_id=current_user.id,
        email=body.email,
        role=body.role,
    )


@router.patch("/{workspace_id}/members/{member_id}", response_model=WorkspaceMemberResponse)
async def update_workspace_member_role(
    workspace_id: UUID,
    member_id: UUID,
    body: WorkspaceMemberRoleRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceMemberResponse:
    return await service.update_member_role(
        session,
        workspace_id=workspace_id,
        member_id=member_id,
        actor_user_id=current_user.id,
        role=body.role,
    )


@router.post("/{workspace_id}/transfer-ownership", response_model=WorkspaceResponse)
async def transfer_workspace_ownership(
    workspace_id: UUID,
    body: WorkspaceOwnershipTransferRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    return await service.transfer_ownership(
        session,
        workspace_id=workspace_id,
        actor_user_id=current_user.id,
        member_id=body.member_id,
    )


@router.delete("/{workspace_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_workspace_member(
    workspace_id: UUID,
    member_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: WorkspaceService = Depends(get_workspace_service),
) -> Response:
    await service.remove_member(session, workspace_id=workspace_id, member_id=member_id, actor_user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{workspace_id}/audit", response_model=WorkspaceAuditEventListResponse)
async def list_workspace_audit_events(
    workspace_id: UUID,
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: WorkspaceService = Depends(get_workspace_service),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> WorkspaceAuditEventListResponse:
    return await service.list_audit_events(
        session,
        workspace_id=workspace_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )


__all__ = [
    "get_workspace_service",
    "router",
]
