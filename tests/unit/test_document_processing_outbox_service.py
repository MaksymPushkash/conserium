from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest
from fastapi import BackgroundTasks

from src.documents.processing import (
    DocumentProcessingService,
    document_processing_outbox_task_id,
)
from src.documents.schemas import DocumentProcessingOutboxRecord
from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.models.document import DocumentModel

if TYPE_CHECKING:
    from src.documents.status_cache import RedisDocumentStatusCache
    from src.worker.dispatcher import CeleryTaskDispatcher


@pytest.mark.asyncio
async def test_document_processing_outbox_drains_pending_item_with_deterministic_task_id() -> None:
    document = _document(status=DocumentStatus.PENDING)
    outbox = _outbox(document_id=document.id)
    repository_session = _FakeSession(document=document, outbox=outbox)
    dispatcher = _RecordingDispatcher()

    result = await _processing_service(repository_session, dispatcher).drain()

    assert result.dispatched == 1
    assert dispatcher.calls == [(str(document.id), document_processing_outbox_task_id(outbox.id))]
    assert repository_session.document_processing_outbox_repo.dispatched == []
    assert repository_session.document_repo.document.status == DocumentStatus.QUEUED


@pytest.mark.asyncio
async def test_document_processing_outbox_does_not_dispatch_when_state_commit_fails() -> None:
    document = _document(status=DocumentStatus.PENDING)
    outbox = _outbox(document_id=document.id)
    repository_session = _FakeSession(document=document, outbox=outbox, fail_after_dispatch_commit=True)
    dispatcher = _RecordingDispatcher()

    result = await _processing_service(repository_session, dispatcher).drain()

    assert result.failed == 1
    assert dispatcher.calls == []
    assert repository_session.document_processing_outbox_repo.failed == [(outbox.id, True)]


@pytest.mark.asyncio
async def test_document_processing_outbox_skips_already_processing_documents() -> None:
    document = _document(status=DocumentStatus.PROCESSING)
    outbox = _outbox(document_id=document.id)
    repository_session = _FakeSession(document=document, outbox=outbox)
    dispatcher = _RecordingDispatcher()

    result = await _processing_service(repository_session, dispatcher).drain()

    assert result.dispatched == 1
    assert dispatcher.calls == []
    assert repository_session.document_processing_outbox_repo.dispatched == [outbox.id]


@pytest.mark.asyncio
async def test_document_processing_outbox_acknowledges_worker_start() -> None:
    document = _document(status=DocumentStatus.QUEUED)
    outbox = _outbox(document_id=document.id, status="dispatching")
    repository_session = _FakeSession(document=document, outbox=outbox)

    should_process = await _processing_service(repository_session, _RecordingDispatcher()).acknowledge(
        task_id=document_processing_outbox_task_id(outbox.id), document_id=document.id
    )

    assert should_process is True
    assert repository_session.document_processing_outbox_repo.dispatched == [outbox.id]


@pytest.mark.asyncio
async def test_document_processing_outbox_skips_duplicate_acknowledged_task() -> None:
    document = _document(status=DocumentStatus.QUEUED)
    outbox = _outbox(document_id=document.id, status="dispatched")
    repository_session = _FakeSession(document=document, outbox=outbox)

    should_process = await _processing_service(repository_session, _RecordingDispatcher()).acknowledge(
        task_id=document_processing_outbox_task_id(outbox.id), document_id=document.id
    )

    assert should_process is False
    assert repository_session.document_processing_outbox_repo.dispatched == []


@pytest.mark.asyncio
async def test_document_processing_request_flushes_outbox_before_background_drain() -> None:
    document = _document(status=DocumentStatus.PENDING)
    outbox = _outbox(document_id=document.id, status="pending")
    repository_session = _FakeSession(document=document, outbox=outbox)
    dispatcher = _RecordingDispatcher()
    background_tasks = BackgroundTasks()

    await _processing_service(repository_session, dispatcher, background_tasks).queue(
        document,
        message="Queued for processing.",
    )

    assert repository_session.commits == 0
    assert repository_session.flushes == 1
    assert dispatcher.calls == []
    assert dispatcher.outbox_drains == 0

    await background_tasks()

    assert dispatcher.outbox_drains == 1


class _FakeSession:
    def __init__(
        self,
        *,
        document: DocumentModel,
        outbox: DocumentProcessingOutboxRecord,
        fail_after_dispatch_commit: bool = False,
    ) -> None:
        self.document_repo = _DocumentRepo(document)
        self.document_processing_outbox_repo = _OutboxRepo(outbox)
        self.fail_after_dispatch_commit = fail_after_dispatch_commit
        self.commits = 0
        self.flushes = 0

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1
        if self.fail_after_dispatch_commit and self.commits == 2:
            raise RuntimeError("commit failed")

    async def flush(self) -> None:
        self.flushes += 1


class _DocumentRepo:
    def __init__(self, document: DocumentModel) -> None:
        self.document = document

    async def get_by_id(self, document_id: UUID) -> DocumentModel | None:
        return self.document if self.document.id == document_id else None

    async def update(self, document: DocumentModel) -> None:
        self.document = document


class _OutboxRepo:
    def __init__(self, outbox: DocumentProcessingOutboxRecord) -> None:
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
    ) -> list[DocumentProcessingOutboxRecord]:
        return [self.outbox]

    async def create_outbox(self, *, document_id: UUID, task_name: str) -> DocumentProcessingOutboxRecord:
        return self.outbox

    async def get_by_id(self, outbox_id: UUID) -> DocumentProcessingOutboxRecord | None:
        return self.outbox if self.outbox.id == outbox_id else None

    async def mark_dispatching(self, outbox_id: UUID, locked_at: datetime) -> DocumentProcessingOutboxRecord:
        self.outbox = _replace_outbox(self.outbox, status="dispatching", locked_at=locked_at)
        return self.outbox

    async def mark_dispatched(self, outbox_id: UUID, dispatched_at: datetime) -> DocumentProcessingOutboxRecord:
        self.dispatched.append(outbox_id)
        self.outbox = _replace_outbox(self.outbox, status="dispatched", dispatched_at=dispatched_at)
        return self.outbox

    async def mark_failed(self, outbox_id: UUID, *, last_error: str, retryable: bool) -> DocumentProcessingOutboxRecord:
        self.failed.append((outbox_id, retryable))
        return self.outbox


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.outbox_drains = 0

    async def dispatch_process_document(self, document_id: str, *, task_id: str | None = None) -> None:
        self.calls.append((document_id, task_id))

    async def dispatch_document_processing_outbox(self) -> None:
        self.outbox_drains += 1


class _StatusCache:
    async def set_status(self, document_id: UUID, status: str, progress: int, message: str) -> None:
        return None


def _processing_service(
    session: _FakeSession,
    dispatcher: _RecordingDispatcher,
    background_tasks: BackgroundTasks | None = None,
) -> DocumentProcessingService:
    return DocumentProcessingService(
        session,  # type: ignore[arg-type]
        session.document_repo,  # type: ignore[arg-type]
        session.document_processing_outbox_repo,  # type: ignore[arg-type]
        cast("RedisDocumentStatusCache", _StatusCache()),
        cast("CeleryTaskDispatcher", dispatcher),
        background_tasks,
    )


def _outbox(*, document_id: UUID, attempts: int = 1, status: str = "processing") -> DocumentProcessingOutboxRecord:
    now = datetime.now(UTC)
    return DocumentProcessingOutboxRecord(
        id=uuid4(),
        document_id=document_id,
        task_name="process_document",
        status=status,
        attempts=attempts,
        locked_at=now,
        last_error=None,
        dispatched_at=None,
        created_at=now,
        updated_at=None,
    )


def _document(*, status: DocumentStatus) -> DocumentModel:
    return DocumentModel(
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


def _replace_outbox(
    outbox: DocumentProcessingOutboxRecord,
    *,
    status: str | None = None,
    locked_at: datetime | None = None,
    dispatched_at: datetime | None = None,
) -> DocumentProcessingOutboxRecord:
    return DocumentProcessingOutboxRecord(
        id=outbox.id,
        document_id=outbox.document_id,
        task_name=outbox.task_name,
        status=status or outbox.status,
        attempts=outbox.attempts,
        locked_at=locked_at if locked_at is not None else outbox.locked_at,
        last_error=outbox.last_error,
        dispatched_at=dispatched_at if dispatched_at is not None else outbox.dispatched_at,
        created_at=outbox.created_at,
        updated_at=outbox.updated_at,
    )
