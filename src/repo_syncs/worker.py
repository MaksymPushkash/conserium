from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.documents.activity_repository import DocumentActivityRepository
from src.documents.document_repository import DocumentRepository
from src.documents.status_cache import RedisDocumentStatusCache
from src.repo_syncs.github_repository_client import GitHubRepositoryClient
from src.repo_syncs.repository import RepoSyncRepository
from src.repo_syncs.service import (
    RepoSyncOutboxDrainer,
    RepoSyncRunner,
)
from src.settings import settings
from src.worker.dependencies import get_worker_redis, get_worker_session_factory
from src.worker.dispatcher import CeleryTaskDispatcher

if TYPE_CHECKING:
    from uuid import UUID

    from src.repo_syncs.schemas import RepoSyncResult

logger = logging.getLogger(__name__)


async def run_due_repo_syncs() -> dict[str, int]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=True)
    try:
        async with factory() as session:
            cutoff = datetime.now(UTC) - timedelta(minutes=settings.REPO_SYNC_INTERVAL_MINUTES)
            repo_syncs = await _list_due_repo_syncs(RepoSyncRepository.from_session(session), cutoff=cutoff)
            handler = RepoSyncRunner(
                session=session,
                document_repo=DocumentRepository.from_session(session),
                document_activity_repo=DocumentActivityRepository.from_session(session),
                repo_sync_repo=RepoSyncRepository.from_session(session),
                github_client=GitHubRepositoryClient(),
                task_dispatcher=CeleryTaskDispatcher(),
            )
            completed = 0
            failed = 0
            for repo_sync in repo_syncs:
                try:
                    await handler(user_id=repo_sync.user_id, repo_sync_id=repo_sync.id, max_files=50)
                    completed += 1
                except Exception as exc:
                    logger.exception("Repo sync failed for %s/%s@%s: %s", repo_sync.owner, repo_sync.repo, repo_sync.branch, exc)
                    failed += 1
            return {"queued": len(repo_syncs), "completed": completed, "failed": failed}
    finally:
        await redis.aclose()


async def run_repo_sync(*, user_id: UUID, repo_sync_id: UUID, max_files: int) -> dict[str, object]:
    factory = get_worker_session_factory()
    async with factory() as session:
        result = await RepoSyncRunner(
            session=session,
            document_repo=DocumentRepository.from_session(session),
            document_activity_repo=DocumentActivityRepository.from_session(session),
            repo_sync_repo=RepoSyncRepository.from_session(session),
            github_client=GitHubRepositoryClient(),
            task_dispatcher=CeleryTaskDispatcher(),
        )(user_id=user_id, repo_sync_id=repo_sync_id, max_files=max_files)
        return {
            "repo_sync_id": str(result.repo_sync.id),
            "created": result.created,
            "updated": result.updated,
            "skipped": result.skipped,
            "deleted": result.deleted,
            "warnings": result.warnings,
        }


async def drain_repo_sync_outbox(*, limit: int = 100) -> dict[str, int]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=True)
    try:
        async with factory() as session:
            handler = RepoSyncOutboxDrainer(
                session=session,
                document_repo=DocumentRepository.from_session(session),
                repo_sync_repo=RepoSyncRepository.from_session(session),
                status_cache=RedisDocumentStatusCache(redis),
                task_dispatcher=CeleryTaskDispatcher(),
            )
            result = await handler(limit=limit)
            return {
                "claimed": result.claimed,
                "dispatched": result.dispatched,
                "failed": result.failed,
                "permanently_failed": result.permanently_failed,
            }
    finally:
        await redis.aclose()


async def _list_due_repo_syncs(repository: RepoSyncRepository, *, cutoff: datetime) -> list[RepoSyncResult]:
    return await repository.list_due_for_sync(
        before=cutoff,
        limit=settings.REPO_SYNC_BATCH_LIMIT,
    )
