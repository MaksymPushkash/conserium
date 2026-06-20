from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.documents.notes import (
    NoteService,
)
from src.documents.processing import DocumentProcessingService
from src.documents.repository import NoteVersionRecord
from src.documents.schemas import CreateNoteDTO, UpdateNoteDTO
from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.models.document import DocumentModel

if TYPE_CHECKING:
    from src.documents.access import DocumentCollectionAccess
    from src.documents.document_repository import DocumentRepository
    from src.documents.status_cache import IDocumentStatusCache
    from src.worker.dispatcher import ITaskDispatcher


@pytest.mark.asyncio
async def test_create_empty_note_stays_ready_without_queueing() -> None:
    user_id = uuid.uuid4()
    repository_session = _FakeSession()
    dispatcher = _RecordingDispatcher()
    service = _note_service(repository_session, _RecordingStatusCache(), dispatcher)

    result = await service.create(CreateNoteDTO(user_id=user_id, title="", content="   "))

    assert result.title == "Untitled"
    assert result.status == DocumentStatus.READY
    assert dispatcher.document_processing_outbox_dispatches == 0
    assert repository_session.document_repo.created[0].raw_content is None


@pytest.mark.asyncio
async def test_update_note_versions_previous_content_and_requeues_processing() -> None:
    user_id = uuid.uuid4()
    note = _note(user_id=user_id, title="Old title", content="Old content")
    repository_session = _FakeSession([note])
    status_cache = _RecordingStatusCache()
    dispatcher = _RecordingDispatcher()
    service = _note_service(repository_session, status_cache, dispatcher)

    result = await service.update(
        UpdateNoteDTO(
            user_id=user_id,
            note_id=note.id,
            title="New title",
            content="New content",
            language="en",
        )
    )

    assert result.title == "New title"
    assert result.status == DocumentStatus.QUEUED
    assert repository_session.note_version_repo.records[0].title == "Old title"
    assert repository_session.note_version_repo.records[0].content == "Old content"
    assert repository_session.document_processing_outbox_repo.created == [(note.id, "process_document")]
    assert dispatcher.document_ids == []
    assert dispatcher.document_processing_outbox_dispatches == 0
    assert status_cache.calls[-1] == ("QUEUED", 0, "Queued note for memory indexing.")


@pytest.mark.asyncio
async def test_restore_empty_note_version_clears_chunks_without_queueing() -> None:
    user_id = uuid.uuid4()
    note = _note(user_id=user_id, title="Current", content="Current content")
    version_id = uuid.uuid4()
    repository_session = _FakeSession([note])
    repository_session.note_version_repo.records.append(
        NoteVersionRecord(
            id=version_id,
            note_id=note.id,
            user_id=user_id,
            version_number=1,
            title="Blank",
            content="",
            created_at=datetime.now(UTC),
        )
    )
    dispatcher = _RecordingDispatcher()
    service = _note_service(repository_session, _RecordingStatusCache(), dispatcher)

    result = await service.restore_version(user_id=user_id, note_id=note.id, version_id=version_id)

    assert result.title == "Blank"
    assert result.content == ""
    assert result.status == DocumentStatus.READY
    assert repository_session.chunk_repo.deleted_document_ids == [note.id]
    assert dispatcher.document_processing_outbox_dispatches == 0


def _note(*, user_id: uuid.UUID, title: str, content: str) -> DocumentModel:
    document = DocumentModel.create(
        id=uuid.uuid4(),
        user_id=user_id,
        collection_id=None,
        title=title,
        type=DocumentType.MARKDOWN,
        raw_content=content,
        word_count=len(content.split()),
        language="en",
    )
    document.mark_ready()
    return document


class _FakeSession:
    def __init__(self, documents: list[DocumentModel] | None = None) -> None:
        self.document_repo = _NoteDocumentRepo(documents or [])
        self.collection_repo = _CollectionRepo()
        self.shared_workspace_repo = _SharedWorkspaceRepo()
        self.document_processing_outbox_repo = _DocumentProcessingOutboxRepo()
        self.note_version_repo = _NoteVersionRepo()
        self.chunk_repo = _ChunkRepo()
        self.commits = 0

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        self.commits += 1


class _NoteDocumentRepo:
    def __init__(self, documents: list[DocumentModel]) -> None:
        self.documents = {document.id: document for document in documents}
        self.created: list[DocumentModel] = []

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentModel | None:
        return self.documents.get(document_id)

    async def create(self, document: DocumentModel) -> None:
        self.created.append(document)
        self.documents[document.id] = document

    async def update(self, document: DocumentModel) -> None:
        self.documents[document.id] = document


class _CollectionRepo:
    async def get_by_id(self, collection_id: uuid.UUID) -> None:
        return None


class _SharedWorkspaceRepo:
    async def get_workspace_member_for_user(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
        return None

    async def get_member_for_user(self, *, collection_id: uuid.UUID, user_id: uuid.UUID) -> None:
        return None


class _DocumentProcessingOutboxRepo:
    def __init__(self) -> None:
        self.created: list[tuple[uuid.UUID, str]] = []
        self.dispatched: list[uuid.UUID] = []

    async def create_outbox(self, *, document_id: uuid.UUID, task_name: str) -> object:
        self.created.append((document_id, task_name))
        return _OutboxRecord(id=uuid.uuid4())

    async def mark_dispatching(self, outbox_id: uuid.UUID, locked_at: object) -> object:
        return _OutboxRecord(id=outbox_id)

    async def mark_dispatched(self, outbox_id: uuid.UUID, dispatched_at: object) -> object:
        self.dispatched.append(outbox_id)
        return _OutboxRecord(id=outbox_id)


@dataclass(frozen=True, slots=True)
class _OutboxRecord:
    id: uuid.UUID


class _NoteVersionRepo:
    def __init__(self) -> None:
        self.records: list[NoteVersionRecord] = []

    async def create(self, version: NoteVersionRecord) -> None:
        self.records.append(version)

    async def list_by_note_id(self, *, note_id: uuid.UUID, user_id: uuid.UUID) -> list[NoteVersionRecord]:
        return [record for record in self.records if record.note_id == note_id and record.user_id == user_id]

    async def get_by_id(
        self,
        *,
        version_id: uuid.UUID,
        note_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> NoteVersionRecord | None:
        return next(
            (
                record
                for record in self.records
                if record.id == version_id and record.note_id == note_id and record.user_id == user_id
            ),
            None,
        )

    async def count_by_note_id(self, note_id: uuid.UUID) -> int:
        return len([record for record in self.records if record.note_id == note_id])


class _ChunkRepo:
    def __init__(self) -> None:
        self.deleted_document_ids: list[uuid.UUID] = []

    async def delete_by_document_id(self, document_id: uuid.UUID) -> None:
        self.deleted_document_ids.append(document_id)


class _RecordingStatusCache:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str]] = []

    async def set_status(self, document_id: uuid.UUID, *, status: str, progress: int, message: str) -> None:
        self.calls.append((status, progress, message))


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.document_ids: list[str] = []
        self.document_processing_outbox_dispatches = 0

    async def dispatch_process_document(self, document_id: str, *, task_id: str | None = None) -> None:
        self.document_ids.append(document_id)

    async def dispatch_document_processing_outbox(self) -> None:
        self.document_processing_outbox_dispatches += 1


def _processing_service(
    session: _FakeSession,
    status_cache: _RecordingStatusCache,
    dispatcher: _RecordingDispatcher,
) -> DocumentProcessingService:
    return DocumentProcessingService(
        session,  # type: ignore[arg-type]
        session.document_repo,  # type: ignore[arg-type]
        session.document_processing_outbox_repo,  # type: ignore[arg-type]
        cast("IDocumentStatusCache", status_cache),
        cast("ITaskDispatcher", dispatcher),
    )


def _note_service(
    session: _FakeSession,
    status_cache: _RecordingStatusCache,
    dispatcher: _RecordingDispatcher,
) -> NoteService:
    return NoteService(
        session,  # type: ignore[arg-type]
        cast("DocumentRepository", session.document_repo),
        cast("DocumentCollectionAccess", session),
        session.note_version_repo,  # type: ignore[arg-type]
        _processing_service(session, status_cache, dispatcher),
        session.chunk_repo,  # type: ignore[arg-type]
    )
