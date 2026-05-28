from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.domain.value_objects.document_status import DocumentStatus

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.dtos.document_processing_outbox_dtos import DocumentProcessingOutboxDTO
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.domain.entities.document_entity import DocumentEntity


DOCUMENT_PROCESSING_TASK_NAME = "process_document"
_MAX_OUTBOX_ATTEMPTS = 5
_OUTBOX_LOCK_TIMEOUT = timedelta(minutes=15)
_OUTBOX_BATCH_LIMIT = 100

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DocumentProcessingOutboxDrainResult:
    claimed: int
    dispatched: int
    failed: int
    permanently_failed: int


class DrainDocumentProcessingOutboxUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
    ) -> None:
        self._uow = uow
        self._status_cache = status_cache
        self._task_dispatcher = task_dispatcher

    async def __call__(self, *, limit: int = _OUTBOX_BATCH_LIMIT) -> DocumentProcessingOutboxDrainResult:
        outbox_items = await self._claim_outbox(limit)
        dispatched = 0
        failed = 0
        permanently_failed = 0

        for outbox in outbox_items:
            try:
                await self._dispatch_outbox_item(outbox)
                dispatched += 1
            except Exception as exc:
                retryable = outbox.attempts < _MAX_OUTBOX_ATTEMPTS
                await self._mark_outbox_failed(outbox, exc, retryable=retryable)
                failed += 1
                if not retryable:
                    permanently_failed += 1
                    await self._mark_document_failed(outbox.document_id, "Document processing dispatch failed after retries.")

        return DocumentProcessingOutboxDrainResult(
            claimed=len(outbox_items),
            dispatched=dispatched,
            failed=failed,
            permanently_failed=permanently_failed,
        )

    async def _claim_outbox(self, limit: int) -> list[DocumentProcessingOutboxDTO]:
        now = datetime.now(UTC)
        async with self._uow:
            outbox_items = await self._uow.document_processing_outbox_repo.claim_batch(
                limit=limit,
                locked_at=now,
                stale_before=now - _OUTBOX_LOCK_TIMEOUT,
                max_attempts=_MAX_OUTBOX_ATTEMPTS,
            )
            await self._uow.commit()
        return outbox_items

    async def _dispatch_outbox_item(self, outbox: DocumentProcessingOutboxDTO) -> None:
        document = await self._load_document(outbox.document_id)
        if document is None:
            await self._mark_outbox_dispatched(outbox)
            return

        if document.status in (DocumentStatus.PROCESSING, DocumentStatus.READY):
            await self._mark_outbox_dispatched(outbox)
            return

        await self._status_cache.set_status(
            outbox.document_id,
            status=DocumentStatus.QUEUED.value,
            progress=0,
            message="Queued for processing.",
        )
        await self._task_dispatcher.dispatch_process_document(
            str(outbox.document_id),
            task_id=document_processing_outbox_task_id(outbox.id),
        )

        async with self._uow:
            document = await self._uow.document_repo.get_by_id(outbox.document_id)
            if document is not None:
                document.mark_queued()
                await self._uow.document_repo.update(document)
            await self._uow.document_processing_outbox_repo.mark_dispatched(outbox.id, datetime.now(UTC))
            await self._uow.commit()

    async def _load_document(self, document_id: UUID) -> DocumentEntity | None:
        async with self._uow:
            return await self._uow.document_repo.get_by_id(document_id)

    async def _mark_outbox_dispatched(self, outbox: DocumentProcessingOutboxDTO) -> None:
        async with self._uow:
            await self._uow.document_processing_outbox_repo.mark_dispatched(outbox.id, datetime.now(UTC))
            await self._uow.commit()

    async def _mark_outbox_failed(
        self,
        outbox: DocumentProcessingOutboxDTO,
        exc: Exception,
        *,
        retryable: bool,
    ) -> None:
        async with self._uow:
            await self._uow.document_processing_outbox_repo.mark_failed(
                outbox.id,
                last_error=_sanitize_outbox_error(exc),
                retryable=retryable,
            )
            await self._uow.commit()

    async def _mark_document_failed(self, document_id: UUID, message: str) -> None:
        try:
            async with self._uow:
                document = await self._uow.document_repo.get_by_id(document_id)
                if document is not None:
                    document.mark_failed()
                    await self._uow.document_repo.update(document)
                await self._uow.commit()
            await self._status_cache.set_status(document_id, status="FAILED", progress=0, message=message)
        except Exception as exc:
            logger.exception(
                "document_processing_failed_state_persistence_failed",
                extra={
                    "document_id": str(document_id),
                    "error_type": type(exc).__name__,
                    "sanitized_error": message,
                },
            )


def document_processing_outbox_task_id(outbox_id: UUID) -> str:
    return f"document-processing-outbox-{outbox_id}"


async def kick_document_processing_outbox_item(
    *,
    outbox_id: UUID,
    document_id: UUID,
    uow: IUnitOfWork,
    task_dispatcher: ITaskDispatcher,
) -> None:
    await task_dispatcher.dispatch_process_document(
        str(document_id),
        task_id=document_processing_outbox_task_id(outbox_id),
    )
    async with uow:
        await uow.document_processing_outbox_repo.mark_dispatched(outbox_id, datetime.now(UTC))
        await uow.commit()


def _sanitize_outbox_error(exc: Exception) -> str:
    message = str(exc).strip() or type(exc).__name__
    return message[:500]
