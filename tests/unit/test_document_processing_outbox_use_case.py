from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest

from src.application.dtos.document_processing_outbox_dtos import DocumentProcessingOutboxDTO
from src.application.use_cases.documents.document_processing_outbox import (
    DrainDocumentProcessingOutboxUseCase,
    document_processing_outbox_task_id,
)
from src.domain.entities.document_entity import DocumentEntity
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


@pytest.mark.asyncio
async def test_document_processing_outbox_drains_pending_item_with_deterministic_task_id() -> None:
    document = _document(status=DocumentStatus.PENDING)
    outbox = _outbox(document_id=document.id)
    uow = _OutboxUow(document=document, outbox=outbox)
    dispatcher = _RecordingDispatcher()

    result = await DrainDocumentProcessingOutboxUseCase(
        cast("IUnitOfWork", uow),
        cast("IDocumentStatusCache", _StatusCache()),
        cast("ITaskDispatcher", dispatcher),
    )()

    assert result.dispatched == 1
    assert dispatcher.calls == [(str(document.id), document_processing_outbox_task_id(outbox.id))]
    assert uow.document_processing_outbox_repo.dispatched == [outbox.id]
    assert uow.document_repo.document.status == DocumentStatus.QUEUED


@pytest.mark.asyncio
async def test_document_processing_outbox_retries_after_post_dispatch_commit_failure() -> None:
    document = _document(status=DocumentStatus.PENDING)
    outbox = _outbox(document_id=document.id)
    uow = _OutboxUow(document=document, outbox=outbox, fail_after_dispatch_commit=True)
    dispatcher = _RecordingDispatcher()

    result = await DrainDocumentProcessingOutboxUseCase(
        cast("IUnitOfWork", uow),
        cast("IDocumentStatusCache", _StatusCache()),
        cast("ITaskDispatcher", dispatcher),
    )()

    assert result.failed == 1
    assert dispatcher.calls == [(str(document.id), document_processing_outbox_task_id(outbox.id))]
    assert uow.document_processing_outbox_repo.failed == [(outbox.id, True)]


@pytest.mark.asyncio
async def test_document_processing_outbox_skips_already_processing_documents() -> None:
    document = _document(status=DocumentStatus.PROCESSING)
    outbox = _outbox(document_id=document.id)
    uow = _OutboxUow(document=document, outbox=outbox)
    dispatcher = _RecordingDispatcher()

    result = await DrainDocumentProcessingOutboxUseCase(
        cast("IUnitOfWork", uow),
        cast("IDocumentStatusCache", _StatusCache()),
        cast("ITaskDispatcher", dispatcher),
    )()

    assert result.dispatched == 1
    assert dispatcher.calls == []
    assert uow.document_processing_outbox_repo.dispatched == [outbox.id]


class _OutboxUow:
    def __init__(
        self,
        *,
        document: DocumentEntity,
        outbox: DocumentProcessingOutboxDTO,
        fail_after_dispatch_commit: bool = False,
    ) -> None:
        self.document_repo = _DocumentRepo(document)
        self.document_processing_outbox_repo = _OutboxRepo(outbox)
        self.fail_after_dispatch_commit = fail_after_dispatch_commit
        self.commits = 0

    async def __aenter__(self) -> _OutboxUow:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1
        if self.fail_after_dispatch_commit and self.commits == 2:
            raise RuntimeError("commit failed")


class _DocumentRepo:
    def __init__(self, document: DocumentEntity) -> None:
        self.document = document

    async def get_by_id(self, document_id: UUID) -> DocumentEntity | None:
        return self.document if self.document.id == document_id else None

    async def update(self, document: DocumentEntity) -> None:
        self.document = document


class _OutboxRepo:
    def __init__(self, outbox: DocumentProcessingOutboxDTO) -> None:
        self.outbox = outbox
        self.dispatched: list[UUID] = []
        self.failed: list[tuple[UUID, bool]] = []

    async def claim_batch(
        self,
        *,
        limit: int,
        locked_at: datetime,
        stale_before: datetime,
        max_attempts: int,
    ) -> list[DocumentProcessingOutboxDTO]:
        return [self.outbox]

    async def mark_dispatched(self, outbox_id: UUID, dispatched_at: datetime) -> DocumentProcessingOutboxDTO:
        self.dispatched.append(outbox_id)
        return self.outbox

    async def mark_failed(self, outbox_id: UUID, *, last_error: str, retryable: bool) -> DocumentProcessingOutboxDTO:
        self.failed.append((outbox_id, retryable))
        return self.outbox


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def dispatch_process_document(self, document_id: str, *, task_id: str | None = None) -> None:
        self.calls.append((document_id, task_id))


class _StatusCache:
    async def set_status(self, document_id: UUID, status: str, progress: int, message: str) -> None:
        return None


def _outbox(*, document_id: UUID, attempts: int = 1) -> DocumentProcessingOutboxDTO:
    now = datetime.now(UTC)
    return DocumentProcessingOutboxDTO(
        id=uuid4(),
        document_id=document_id,
        task_name="process_document",
        status="processing",
        attempts=attempts,
        locked_at=now,
        last_error=None,
        dispatched_at=None,
        created_at=now,
        updated_at=None,
    )


def _document(*, status: DocumentStatus) -> DocumentEntity:
    return DocumentEntity(
        id=uuid4(),
        user_id=uuid4(),
        collection_id=None,
        title="Queued document",
        type=DocumentType.TEXT,
        status=status,
        source_url=None,
        file_path=None,
        file_size_bytes=None,
        raw_content="Saved text",
        summary=None,
        word_count=2,
        language="en",
        doc_embedding=None,
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=datetime.now(UTC),
        updated_at=None,
    )
