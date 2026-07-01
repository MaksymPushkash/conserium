from uuid import UUID

from fastapi import Depends, status

from src.auth.auth import CurrentUser
from src.postgres import AsyncSession, get_db_session
from src.repo_syncs.dependencies import get_repo_sync_service, get_task_dispatcher
from src.repo_syncs.schemas import (
    CreateRepoSyncRequest,
    RepoSyncListResponse,
    RepoSyncResponse,
    RepoSyncRunResponse,
    RunRepoSyncRequest,
)
from src.repo_syncs.service import RepoSyncService
from src.routing import APIRouter
from src.worker.dispatcher import TaskiqTaskDispatcher

router = APIRouter(prefix="/repo-syncs", tags=["repo-syncs"])


@router.get("", response_model=RepoSyncListResponse)
async def list_repo_syncs(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: RepoSyncService = Depends(get_repo_sync_service),
) -> RepoSyncListResponse:
    return await service.list(session, user_id=current_user.id)


@router.post("", response_model=RepoSyncResponse, status_code=status.HTTP_201_CREATED)
async def create_repo_sync(
    body: CreateRepoSyncRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: RepoSyncService = Depends(get_repo_sync_service),
) -> RepoSyncResponse:
    return await service.create(session, user_id=current_user.id, body=body)


@router.post("/{repo_sync_id}/run", response_model=RepoSyncRunResponse)
async def run_repo_sync(
    repo_sync_id: UUID,
    body: RunRepoSyncRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: RepoSyncService = Depends(get_repo_sync_service),
    task_dispatcher: TaskiqTaskDispatcher = Depends(get_task_dispatcher),
) -> RepoSyncRunResponse:
    return await service.queue_run(
        session,
        user_id=current_user.id,
        repo_sync_id=repo_sync_id,
        max_files=body.max_files,
        task_dispatcher=task_dispatcher,
    )


__all__ = ["router"]
