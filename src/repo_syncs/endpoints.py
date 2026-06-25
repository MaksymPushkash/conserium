from uuid import UUID

from fastapi import Depends, status

from src.auth.auth import CurrentUser
from src.repo_syncs.dependencies import get_repo_sync_executor, get_repo_sync_service
from src.repo_syncs.schemas import (
    CreateRepoSyncRequest,
    RepoSyncListResponse,
    RepoSyncResponse,
    RepoSyncRunResponse,
    RunRepoSyncRequest,
)
from src.repo_syncs.service import RepoSyncExecutor, RepoSyncService
from src.routing import APIRouter

router = APIRouter(prefix="/repo-syncs", tags=["repo-syncs"])


@router.get("", response_model=RepoSyncListResponse)
async def list_repo_syncs(
    current_user: CurrentUser,
    service: RepoSyncService = Depends(get_repo_sync_service),
) -> RepoSyncListResponse:
    return await service.list(user_id=current_user.id)


@router.post("", response_model=RepoSyncResponse, status_code=status.HTTP_201_CREATED)
async def create_repo_sync(
    body: CreateRepoSyncRequest,
    current_user: CurrentUser,
    service: RepoSyncService = Depends(get_repo_sync_service),
) -> RepoSyncResponse:
    return await service.create(user_id=current_user.id, body=body)


@router.post("/{repo_sync_id}/run", response_model=RepoSyncRunResponse)
async def run_repo_sync(
    repo_sync_id: UUID,
    body: RunRepoSyncRequest,
    current_user: CurrentUser,
    executor: RepoSyncExecutor = Depends(get_repo_sync_executor),
) -> RepoSyncRunResponse:
    return await executor.run(user_id=current_user.id, repo_sync_id=repo_sync_id, body=body)


__all__ = ["router"]
