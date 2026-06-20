from uuid import UUID

from fastapi import Depends, Query, Response, status

from src.auth.auth import CurrentUser
from src.collections.schemas import (
    CollectionAuditEventListResponse,
    CollectionListResponse,
    CollectionMemberListResponse,
    CollectionMemberRequest,
    CollectionMemberResponse,
    CollectionMemberRoleRequest,
    CollectionRequest,
    CollectionResponse,
    CollectionShareResponse,
    CollectionShareSettingsRequest,
    CollectionWorkspaceResponse,
    PublicAskEventListResponse,
)
from src.collections.service import (
    CollectionService,
    CollectionShareService,
    collection_shares,
    collections,
)
from src.postgres import AsyncReadSession, AsyncSession, get_db_read_session, get_db_session
from src.routing import APIRouter

router = APIRouter(prefix="/collections", tags=["collections"])


def get_collection_share_service() -> CollectionShareService:
    return collection_shares


def get_collection_service() -> CollectionService:
    return collections


@router.post("", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_collection(
    body: CollectionRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: CollectionService = Depends(get_collection_service),
) -> CollectionResponse:
    return await service.create(
        session,
        user_id=current_user.id,
        name=body.name,
        workspace_id=body.workspace_id,
        description=body.description,
        color=body.color,
    )


@router.get("", response_model=CollectionListResponse)
async def list_collections(
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: CollectionService = Depends(get_collection_service),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    workspace_id: UUID | None = Query(default=None),
) -> CollectionListResponse:
    return await service.list(
        session,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        workspace_id=workspace_id,
    )


@router.get("/{collection_id}/workspace", response_model=CollectionWorkspaceResponse)
async def get_collection_workspace(
    collection_id: UUID,
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: CollectionService = Depends(get_collection_service),
) -> CollectionWorkspaceResponse:
    return await service.workspace(session, user_id=current_user.id, collection_id=collection_id)


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: UUID,
    body: CollectionRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: CollectionService = Depends(get_collection_service),
) -> CollectionResponse:
    return await service.update(
        session,
        user_id=current_user.id,
        collection_id=collection_id,
        name=body.name,
        description=body.description,
        color=body.color,
    )


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: CollectionService = Depends(get_collection_service),
) -> Response:
    await service.delete(session, user_id=current_user.id, collection_id=collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{collection_id}/members", response_model=CollectionMemberListResponse)
async def list_collection_members(
    collection_id: UUID,
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: CollectionService = Depends(get_collection_service),
) -> CollectionMemberListResponse:
    return await service.list_members(session, collection_id=collection_id, user_id=current_user.id)


@router.post("/{collection_id}/members", response_model=CollectionMemberResponse, status_code=status.HTTP_201_CREATED)
async def invite_collection_member(
    collection_id: UUID,
    body: CollectionMemberRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: CollectionService = Depends(get_collection_service),
) -> CollectionMemberResponse:
    return await service.invite_member(
        session,
        collection_id=collection_id,
        actor_user_id=current_user.id,
        email=body.email,
        role=body.role,
    )


@router.patch("/{collection_id}/members/{member_id}", response_model=CollectionMemberResponse)
async def update_collection_member_role(
    collection_id: UUID,
    member_id: UUID,
    body: CollectionMemberRoleRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: CollectionService = Depends(get_collection_service),
) -> CollectionMemberResponse:
    return await service.update_member_role(
        session,
        collection_id=collection_id,
        member_id=member_id,
        actor_user_id=current_user.id,
        role=body.role,
    )


@router.delete("/{collection_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_collection_member(
    collection_id: UUID,
    member_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: CollectionService = Depends(get_collection_service),
) -> Response:
    await service.remove_member(session, collection_id=collection_id, member_id=member_id, actor_user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{collection_id}/audit", response_model=CollectionAuditEventListResponse)
async def list_collection_audit_events(
    collection_id: UUID,
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: CollectionService = Depends(get_collection_service),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> CollectionAuditEventListResponse:
    return await service.list_audit_events(
        session,
        collection_id=collection_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )


@router.get("/{collection_id}/share", response_model=CollectionShareResponse | None)
async def get_collection_share(
    collection_id: UUID,
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: CollectionShareService = Depends(get_collection_share_service),
) -> CollectionShareResponse | None:
    return await service.get_share(session, user_id=current_user.id, collection_id=collection_id)


@router.post("/{collection_id}/share", response_model=CollectionShareResponse, status_code=status.HTTP_201_CREATED)
async def create_collection_share(
    collection_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: CollectionShareService = Depends(get_collection_share_service),
) -> CollectionShareResponse:
    return await service.create_share(session, user_id=current_user.id, collection_id=collection_id)


@router.get("/{collection_id}/share/events", response_model=PublicAskEventListResponse)
async def get_collection_share_ask_events(
    collection_id: UUID,
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: CollectionShareService = Depends(get_collection_share_service),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PublicAskEventListResponse:
    return await service.list_ask_events(
        session,
        user_id=current_user.id,
        collection_id=collection_id,
        limit=limit,
        offset=offset,
    )


@router.patch("/{collection_id}/share", response_model=CollectionShareResponse)
async def update_collection_share_settings(
    collection_id: UUID,
    body: CollectionShareSettingsRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: CollectionShareService = Depends(get_collection_share_service),
) -> CollectionShareResponse:
    return await service.update_share_settings(
        session,
        user_id=current_user.id,
        collection_id=collection_id,
        ask_enabled=body.ask_enabled,
        daily_ask_limit=body.daily_ask_limit,
    )


@router.delete("/{collection_id}/share", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_collection_share(
    collection_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: CollectionShareService = Depends(get_collection_share_service),
) -> Response:
    await service.revoke_share(session, user_id=current_user.id, collection_id=collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["get_collection_service", "get_collection_share_service", "router"]
