from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, status

from src.application.use_cases.repo_syncs import CreateRepoSyncUseCase, ListRepoSyncsUseCase, RunRepoSyncUseCase
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.repo_sync_mapper import (
    to_create_repo_sync_dto,
    to_repo_sync_list_response,
    to_repo_sync_response,
    to_repo_sync_run_response,
    to_run_repo_sync_dto,
)
from src.presentation.schemas.repo_sync import (
    CreateRepoSyncRequest,
    RepoSyncListResponse,
    RepoSyncResponse,
    RepoSyncRunResponse,
    RunRepoSyncRequest,
)

router = APIRouter(prefix="/repo-syncs", tags=["repo-syncs"])


@router.get("", response_model=RepoSyncListResponse)
@inject
async def list_repo_syncs(
    current_user: CurrentUser,
    use_case: FromDishka[ListRepoSyncsUseCase],
) -> RepoSyncListResponse:
    result = await use_case(user_id=current_user.id)
    return to_repo_sync_list_response(result)


@router.post("", response_model=RepoSyncResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_repo_sync(
    body: CreateRepoSyncRequest,
    current_user: CurrentUser,
    use_case: FromDishka[CreateRepoSyncUseCase],
) -> RepoSyncResponse:
    result = await use_case(to_create_repo_sync_dto(body, current_user.id))
    return to_repo_sync_response(result)


@router.post("/{repo_sync_id}/run", response_model=RepoSyncRunResponse)
@inject
async def run_repo_sync(
    repo_sync_id: UUID,
    body: RunRepoSyncRequest,
    current_user: CurrentUser,
    use_case: FromDishka[RunRepoSyncUseCase],
) -> RepoSyncRunResponse:
    result = await use_case(to_run_repo_sync_dto(body, current_user.id, repo_sync_id))
    return to_repo_sync_run_response(result)
