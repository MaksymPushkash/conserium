from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from uuid import UUID

from src.collections.repository import CollectionRepository
from src.kit.exceptions import (
    ResourceNotFoundException,
)
from src.repo_syncs.helpers import (
    DEFAULT_EXCLUDE_PATHS,
    DEFAULT_INCLUDE_PATHS,
    GitHubRepoRef,
    filter_repo_files,
    normalize_max_files,
    normalize_repo_path_patterns,
    parse_github_repo_url,
    repo_sync_outbox_task_id,
    sanitize_outbox_error,
    sanitize_repo_sync_error,
    sanitized_repo_sync_exception,
    stale_repo_items,
    unique_repo_files,
)
from src.repo_syncs.outbox import RepoSyncOutboxDrainer, RepoSyncOutboxDrainResult
from src.repo_syncs.repository import RepoSyncRepository
from src.repo_syncs.responses import (
    to_repo_sync_list_response,
    to_repo_sync_response,
    to_repo_sync_run_response,
)
from src.repo_syncs.runner import RepoSyncRunner
from src.repo_syncs.schemas import (
    CreateRepoSyncRequest,
    RepoSyncListResponse,
    RepoSyncListResult,
    RepoSyncResponse,
    RepoSyncRunResponse,
    RepoSyncRunResult,
)

if TYPE_CHECKING:
    from src.postgres import AsyncSession
    from src.worker.dispatcher import TaskiqTaskDispatcher


class RepoSyncService:
    async def list(self, session: AsyncSession, *, user_id: UUID) -> RepoSyncListResponse:
        items = await RepoSyncRepository.from_session(session).list_by_user_id(user_id)
        return to_repo_sync_list_response(RepoSyncListResult(items=items))

    async def create(self, session: AsyncSession, *, user_id: UUID, body: CreateRepoSyncRequest) -> RepoSyncResponse:
        collection_repo = CollectionRepository.from_session(session)
        repo_sync_repo = RepoSyncRepository.from_session(session)
        repo_ref = parse_github_repo_url(body.repo_url)
        branch = body.branch.strip() or "main"
        include_paths = normalize_repo_path_patterns(body.include_paths, DEFAULT_INCLUDE_PATHS)
        exclude_paths = normalize_repo_path_patterns(body.exclude_paths, DEFAULT_EXCLUDE_PATHS)
        collection = await collection_repo.get_by_id(body.collection_id)
        if collection is None or collection.user_id != user_id:
            raise ResourceNotFoundException("collection not found")
        existing = await repo_sync_repo.get_by_repo(
            user_id=user_id,
            owner=repo_ref.owner,
            repo=repo_ref.repo,
            branch=branch,
        )
        if existing is not None:
            existing = await repo_sync_repo.update_filters(
                repo_sync_id=existing.id,
                include_paths=include_paths,
                exclude_paths=exclude_paths,
            )
            await session.flush()
            return to_repo_sync_response(existing)
        repo_sync = await repo_sync_repo.create(
            id=uuid.uuid4(),
            user_id=user_id,
            collection_id=body.collection_id,
            provider="github",
            owner=repo_ref.owner,
            repo=repo_ref.repo,
            branch=branch,
            include_paths=include_paths,
            exclude_paths=exclude_paths,
        )
        await session.flush()
        return to_repo_sync_response(repo_sync)

    async def queue_run(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        repo_sync_id: UUID,
        max_files: int,
        task_dispatcher: TaskiqTaskDispatcher,
    ) -> RepoSyncRunResponse:
        repo_sync_repo = RepoSyncRepository.from_session(session)
        repo_sync = await repo_sync_repo.get_by_id(repo_sync_id)
        if repo_sync is None or repo_sync.user_id != user_id:
            raise ResourceNotFoundException("repo sync not found")
        normalize_max_files(max_files)
        repo_sync = await repo_sync_repo.update_state(
            repo_sync_id=repo_sync.id,
            status="queued",
            last_error=None,
        )
        await task_dispatcher.dispatch_repo_sync(
            user_id=str(user_id),
            repo_sync_id=str(repo_sync_id),
            max_files=max_files,
        )
        await session.flush()
        return to_repo_sync_run_response(
            RepoSyncRunResult(
                repo_sync=repo_sync,
                created=0,
                updated=0,
                skipped=0,
                deleted=0,
                warnings=["Repo sync queued."],
            )
        )


__all__ = [
    "GitHubRepoRef",
    "RepoSyncOutboxDrainResult",
    "RepoSyncOutboxDrainer",
    "RepoSyncRunner",
    "RepoSyncService",
    "filter_repo_files",
    "normalize_max_files",
    "normalize_repo_path_patterns",
    "parse_github_repo_url",
    "repo_sync_outbox_task_id",
    "sanitize_outbox_error",
    "sanitize_repo_sync_error",
    "sanitized_repo_sync_exception",
    "stale_repo_items",
    "to_repo_sync_list_response",
    "to_repo_sync_response",
    "to_repo_sync_run_response",
    "unique_repo_files",
]
