from src.repo_syncs.schemas import (
    RepoSyncListResponse,
    RepoSyncListResult,
    RepoSyncResponse,
    RepoSyncResult,
    RepoSyncRunResponse,
    RepoSyncRunResult,
)


def to_repo_sync_response(dto: RepoSyncResult) -> RepoSyncResponse:
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


def to_repo_sync_list_response(dto: RepoSyncListResult) -> RepoSyncListResponse:
    return RepoSyncListResponse(items=[to_repo_sync_response(item) for item in dto.items])


def to_repo_sync_run_response(dto: RepoSyncRunResult) -> RepoSyncRunResponse:
    return RepoSyncRunResponse(
        repo_sync=to_repo_sync_response(dto.repo_sync),
        created=dto.created,
        updated=dto.updated,
        skipped=dto.skipped,
        deleted=dto.deleted,
        warnings=dto.warnings,
    )


__all__ = ["to_repo_sync_list_response", "to_repo_sync_response", "to_repo_sync_run_response"]
