from uuid import UUID

from fastapi import Depends, Query, Response, status

from src.auth.auth import CurrentUser
from src.drafts.schemas import (
    DraftDetailResponse,
    DraftGenerateRequest,
    DraftListResponse,
    DraftOutlineResponse,
    DraftResponse,
    DraftTemplateListResponse,
    DraftVersionListResponse,
)
from src.drafts.service import DraftService, get_draft_service
from src.routing import APIRouter

router = APIRouter(prefix="/drafts", tags=["drafts"])


@router.get("", response_model=DraftListResponse)
async def list_drafts(
    current_user: CurrentUser,
    service: DraftService = Depends(get_draft_service),
    collection_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> DraftListResponse:
    return await service.list(user_id=current_user.id, collection_id=collection_id, limit=limit, offset=offset)


@router.get("/templates", response_model=DraftTemplateListResponse)
async def list_draft_templates(
    service: DraftService = Depends(get_draft_service),
) -> DraftTemplateListResponse:
    return await service.list_templates()


@router.post("/outline", response_model=DraftOutlineResponse)
async def generate_draft_outline(
    current_user: CurrentUser,
    body: DraftGenerateRequest,
    service: DraftService = Depends(get_draft_service),
) -> DraftOutlineResponse:
    return await service.generate_outline(user_id=current_user.id, body=body)


@router.post("/generate", response_model=DraftResponse)
async def generate_draft(
    current_user: CurrentUser,
    body: DraftGenerateRequest,
    service: DraftService = Depends(get_draft_service),
) -> DraftResponse:
    return await service.generate(user_id=current_user.id, body=body)


@router.get("/{draft_id}", response_model=DraftDetailResponse)
async def get_draft(
    draft_id: UUID,
    current_user: CurrentUser,
    service: DraftService = Depends(get_draft_service),
) -> DraftDetailResponse:
    return await service.get(user_id=current_user.id, draft_id=draft_id)


@router.get("/{draft_id}/versions", response_model=DraftVersionListResponse)
async def list_draft_versions(
    draft_id: UUID,
    current_user: CurrentUser,
    service: DraftService = Depends(get_draft_service),
) -> DraftVersionListResponse:
    return await service.list_versions(user_id=current_user.id, draft_id=draft_id)


@router.post("/{draft_id}/versions/{version_id}/restore", response_model=DraftDetailResponse)
async def restore_draft_version(
    draft_id: UUID,
    version_id: UUID,
    current_user: CurrentUser,
    service: DraftService = Depends(get_draft_service),
) -> DraftDetailResponse:
    return await service.restore_version(user_id=current_user.id, draft_id=draft_id, version_id=version_id)


@router.delete("/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    draft_id: UUID,
    current_user: CurrentUser,
    service: DraftService = Depends(get_draft_service),
) -> Response:
    await service.delete(user_id=current_user.id, draft_id=draft_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
