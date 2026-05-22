from uuid import UUID

from src.application.dtos.repo_sync_dtos import (
    CreateRepoSyncDTO,
    RepoSyncDTO,
    RepoSyncListDTO,
    RepoSyncRunResultDTO,
    RunRepoSyncDTO,
)
from src.presentation.schemas.repo_sync import (
    CreateRepoSyncRequest,
    RepoSyncListResponse,
    RepoSyncResponse,
    RepoSyncRunResponse,
    RunRepoSyncRequest,
)


def to_create_repo_sync_dto(body: CreateRepoSyncRequest, user_id: UUID) -> CreateRepoSyncDTO:
    return CreateRepoSyncDTO(
        user_id=user_id,
        collection_id=body.collection_id,
        repo_url=body.repo_url,
        branch=body.branch,
        include_paths=body.include_paths,
        exclude_paths=body.exclude_paths,
    )


def to_run_repo_sync_dto(body: RunRepoSyncRequest, user_id: UUID, repo_sync_id: UUID) -> RunRepoSyncDTO:
    return RunRepoSyncDTO(user_id=user_id, repo_sync_id=repo_sync_id, max_files=body.max_files)


def to_repo_sync_response(dto: RepoSyncDTO) -> RepoSyncResponse:
    return RepoSyncResponse(
        id=dto.id,
        collection_id=dto.collection_id,
        provider=dto.provider,
        owner=dto.owner,
        repo=dto.repo,
        branch=dto.branch,
        include_paths=dto.include_paths,
        exclude_paths=dto.exclude_paths,
        status=dto.status,
        last_error=dto.last_error,
        last_synced_at=dto.last_synced_at,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_repo_sync_list_response(dto: RepoSyncListDTO) -> RepoSyncListResponse:
    return RepoSyncListResponse(items=[to_repo_sync_response(item) for item in dto.items])


def to_repo_sync_run_response(dto: RepoSyncRunResultDTO) -> RepoSyncRunResponse:
    return RepoSyncRunResponse(
        repo_sync=to_repo_sync_response(dto.repo_sync),
        created=dto.created,
        updated=dto.updated,
        skipped=dto.skipped,
        deleted=dto.deleted,
        warnings=dto.warnings,
    )
