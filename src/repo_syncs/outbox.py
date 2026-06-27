from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.documents.status import DocumentStatus
from src.repo_syncs.helpers import repo_sync_outbox_task_id, sanitize_outbox_error

if TYPE_CHECKING:
    from uuid import UUID

    from src.documents.document_repository import DocumentRepository
    from src.documents.status_cache import RedisDocumentStatusCache
    from src.models.document import DocumentModel
    from src.postgres import AsyncSession
    from src.repo_syncs.repository import RepoSyncRepository
    from src.repo_syncs.schemas import RepoSyncOutboxRecord
    from src.worker.dispatcher import CeleryTaskDispatcher


logger = logging.getLogger(__name__)

MAX_OUTBOX_ATTEMPTS = 5
OUTBOX_LOCK_TIMEOUT = timedelta(minutes=15)
OUTBOX_BATCH_LIMIT = 100


@dataclass(frozen=True, slots=True)
class RepoSyncOutboxDrainResult:
    claimed: int
    dispatched: int
    failed: int
    permanently_failed: int


class RepoSyncOutboxDrainer:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        repo_sync_repo: RepoSyncRepository,
        status_cache: RedisDocumentStatusCache,
        task_dispatcher: CeleryTaskDispatcher,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._repo_sync_repo = repo_sync_repo
        self._status_cache = status_cache
        self._task_dispatcher = task_dispatcher

    async def __call__(self, *, limit: int = OUTBOX_BATCH_LIMIT) -> RepoSyncOutboxDrainResult:
        outbox_items = await self._claim_outbox(limit)
        dispatched = 0
        failed = 0
        permanently_failed = 0

        for outbox in outbox_items:
            try:
                await self._dispatch_outbox_item(outbox)
                dispatched += 1
            except Exception as exc:
                retryable = outbox.attempts < MAX_OUTBOX_ATTEMPTS
                await self._mark_outbox_failed(outbox, exc, retryable=retryable)
                failed += 1
                if not retryable:
                    permanently_failed += 1
                    await self._mark_repo_sync_failed(outbox.repo_sync_id, "GitHub sync dispatch failed after retries.")

        return RepoSyncOutboxDrainResult(
            claimed=len(outbox_items),
            dispatched=dispatched,
            failed=failed,
            permanently_failed=permanently_failed,
        )

    async def _claim_outbox(self, limit: int) -> list[RepoSyncOutboxRecord]:
        now = datetime.now(UTC)
        outbox_items = await self._repo_sync_repo.claim_outbox_batch(
            limit=limit,
            locked_at=now,
            stale_before=now - OUTBOX_LOCK_TIMEOUT,
            max_attempts=MAX_OUTBOX_ATTEMPTS,
        )
        await self._session.commit()
        return outbox_items

    async def _dispatch_outbox_item(self, outbox: RepoSyncOutboxRecord) -> None:
        document = await self._load_document(outbox.document_id)
        if document is None:
            await self._mark_outbox_dispatched(outbox)
            return

        if document.status in (DocumentStatus.QUEUED, DocumentStatus.PROCESSING, DocumentStatus.READY):
            await self._mark_outbox_dispatched(outbox)
            return

        await self._status_cache.set_status(
            outbox.document_id,
            status=DocumentStatus.QUEUED.value,
            progress=0,
            message="Queued from GitHub sync.",
        )
        await self._task_dispatcher.dispatch_process_document(
            str(outbox.document_id),
            task_id=repo_sync_outbox_task_id(outbox.id),
        )

        document = await self._document_repo.get_by_id(outbox.document_id)
        if document is not None:
            document.mark_queued()
            await self._document_repo.update(document)
        await self._repo_sync_repo.mark_outbox_dispatched(outbox.id, datetime.now(UTC))
        active_outbox = await self._repo_sync_repo.has_active_outbox(outbox.repo_sync_id)
        if not active_outbox:
            await self._repo_sync_repo.update_state(
                repo_sync_id=outbox.repo_sync_id,
                status="completed",
                last_error=None,
                last_synced_at=datetime.now(UTC),
            )
        await self._session.commit()

    async def _load_document(self, document_id: UUID) -> DocumentModel | None:
        return await self._document_repo.get_by_id(document_id)

    async def _mark_outbox_dispatched(self, outbox: RepoSyncOutboxRecord) -> None:
        await self._repo_sync_repo.mark_outbox_dispatched(outbox.id, datetime.now(UTC))
        active_outbox = await self._repo_sync_repo.has_active_outbox(outbox.repo_sync_id)
        if not active_outbox:
            await self._repo_sync_repo.update_state(
                repo_sync_id=outbox.repo_sync_id,
                status="completed",
                last_error=None,
                last_synced_at=datetime.now(UTC),
            )
        await self._session.commit()

    async def _mark_outbox_failed(self, outbox: RepoSyncOutboxRecord, exc: Exception, *, retryable: bool) -> None:
        await self._repo_sync_repo.mark_outbox_failed(
            outbox.id,
            last_error=sanitize_outbox_error(exc),
            retryable=retryable,
        )
        await self._session.commit()

    async def _mark_repo_sync_failed(self, repo_sync_id: UUID, message: str) -> None:
        try:
            await self._repo_sync_repo.update_state(repo_sync_id=repo_sync_id, status="failed", last_error=message)
            await self._session.commit()
        except Exception as exc:
            logger.exception(
                "repo_sync_failed_state_persistence_failed",
                extra={
                    "repo_sync_id": str(repo_sync_id),
                    "error_type": type(exc).__name__,
                    "sanitized_error": message,
                },
            )


__all__ = ["OUTBOX_BATCH_LIMIT", "RepoSyncOutboxDrainResult", "RepoSyncOutboxDrainer"]
