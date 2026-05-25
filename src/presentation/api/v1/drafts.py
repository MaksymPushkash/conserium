from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, status

from src.application.use_cases.drafts import (
    DeleteDraftUseCase,
    GenerateDraftOutlineUseCase,
    GenerateDraftUseCase,
    GetDraftUseCase,
    ListDraftsUseCase,
    ListDraftTemplatesUseCase,
    ListDraftVersionsUseCase,
    RestoreDraftVersionUseCase,
)
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.draft_mapper import (
    to_draft_detail_response,
    to_draft_generate_dto,
    to_draft_list_response,
    to_draft_outline_response,
    to_draft_response,
    to_draft_template_list_response,
    to_draft_version_list_response,
)
from src.presentation.schemas.draft import (
    DraftDetailResponse,
    DraftGenerateRequest,
    DraftListResponse,
    DraftOutlineResponse,
    DraftResponse,
    DraftTemplateListResponse,
    DraftVersionListResponse,
)

router = APIRouter(prefix="/drafts", tags=["drafts"])


@router.get("", response_model=DraftListResponse)
@inject
async def list_drafts(
    current_user: CurrentUser,
    use_case: FromDishka[ListDraftsUseCase],
    collection_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> DraftListResponse:
    result = await use_case(user_id=current_user.id, collection_id=collection_id, limit=limit, offset=offset)
    return to_draft_list_response(result)


@router.get("/templates", response_model=DraftTemplateListResponse)
@inject
async def list_draft_templates(
    use_case: FromDishka[ListDraftTemplatesUseCase],
) -> DraftTemplateListResponse:
    result = await use_case()
    return to_draft_template_list_response(result)


@router.post("/outline", response_model=DraftOutlineResponse)
@inject
async def generate_draft_outline(
    current_user: CurrentUser,
    body: DraftGenerateRequest,
    use_case: FromDishka[GenerateDraftOutlineUseCase],
) -> DraftOutlineResponse:
    result = await use_case(to_draft_generate_dto(body, current_user.id))
    return to_draft_outline_response(result)


@router.post("/generate", response_model=DraftResponse)
@inject
async def generate_draft(
    current_user: CurrentUser,
    body: DraftGenerateRequest,
    use_case: FromDishka[GenerateDraftUseCase],
) -> DraftResponse:
    result = await use_case(to_draft_generate_dto(body, current_user.id))
    return to_draft_response(result)


@router.get("/{draft_id}", response_model=DraftDetailResponse)
@inject
async def get_draft(
    draft_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[GetDraftUseCase],
) -> DraftDetailResponse:
    result = await use_case(user_id=current_user.id, draft_id=draft_id)
    return to_draft_detail_response(result)


@router.get("/{draft_id}/versions", response_model=DraftVersionListResponse)
@inject
async def list_draft_versions(
    draft_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[ListDraftVersionsUseCase],
) -> DraftVersionListResponse:
    result = await use_case(user_id=current_user.id, draft_id=draft_id)
    return to_draft_version_list_response(result)


@router.post("/{draft_id}/versions/{version_id}/restore", response_model=DraftDetailResponse)
@inject
async def restore_draft_version(
    draft_id: UUID,
    version_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[RestoreDraftVersionUseCase],
) -> DraftDetailResponse:
    result = await use_case(user_id=current_user.id, draft_id=draft_id, version_id=version_id)
    return to_draft_detail_response(result)


@router.delete("/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_draft(
    draft_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[DeleteDraftUseCase],
) -> None:
    await use_case(user_id=current_user.id, draft_id=draft_id)
