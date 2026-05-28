from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.application.dtos.note_dtos import CreateNoteDTO, UpdateNoteDTO
from src.application.ports.persistence.note_version_repository import NoteVersionRecord
from src.application.use_cases.documents.notes import CreateNoteUseCase, RestoreNoteVersionUseCase, UpdateNoteUseCase
from src.domain.entities.document_entity import DocumentEntity
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


@pytest.mark.asyncio
async def test_create_empty_note_stays_ready_without_queueing() -> None:
    user_id = uuid.uuid4()
    uow = _NoteUow()
    dispatcher = _RecordingDispatcher()
    use_case = CreateNoteUseCase(
        cast("IUnitOfWork", uow),
        cast("IDocumentStatusCache", _RecordingStatusCache()),
        cast("ITaskDispatcher", dispatcher),
    )

    result = await use_case(CreateNoteDTO(user_id=user_id, title="", content="   "))

    assert result.title == "Untitled"
    assert result.status == DocumentStatus.READY
    assert dispatcher.document_processing_outbox_dispatches == 0
    assert uow.document_repo.created[0].raw_content is None


@pytest.mark.asyncio
async def test_update_note_versions_previous_content_and_requeues_processing() -> None:
    user_id = uuid.uuid4()
    note = _note(user_id=user_id, title="Old title", content="Old content")
    uow = _NoteUow([note])
    status_cache = _RecordingStatusCache()
    dispatcher = _RecordingDispatcher()
    use_case = UpdateNoteUseCase(
        cast("IUnitOfWork", uow),
        cast("IDocumentStatusCache", status_cache),
        cast("ITaskDispatcher", dispatcher),
    )

    result = await use_case(
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
    assert uow.note_version_repo.records[0].title == "Old title"
    assert uow.note_version_repo.records[0].content == "Old content"
    assert uow.document_processing_outbox_repo.created == [(note.id, "process_document")]
    assert dispatcher.document_ids == [str(note.id)]
    assert dispatcher.document_processing_outbox_dispatches == 0
    assert status_cache.calls[-1] == ("QUEUED", 0, "Queued note for memory indexing.")


@pytest.mark.asyncio
async def test_restore_empty_note_version_clears_chunks_without_queueing() -> None:
    user_id = uuid.uuid4()
    note = _note(user_id=user_id, title="Current", content="Current content")
    version_id = uuid.uuid4()
    uow = _NoteUow([note])
    uow.note_version_repo.records.append(
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
    use_case = RestoreNoteVersionUseCase(
        cast("IUnitOfWork", uow),
        cast("IDocumentStatusCache", _RecordingStatusCache()),
        cast("ITaskDispatcher", dispatcher),
    )

    result = await use_case(user_id=user_id, note_id=note.id, version_id=version_id)

    assert result.title == "Blank"
    assert result.content == ""
    assert result.status == DocumentStatus.READY
    assert uow.chunk_repo.deleted_document_ids == [note.id]
    assert dispatcher.document_processing_outbox_dispatches == 0


def _note(*, user_id: uuid.UUID, title: str, content: str) -> DocumentEntity:
    document = DocumentEntity.create(
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


class _NoteUow:
    def __init__(self, documents: list[DocumentEntity] | None = None) -> None:
        self.document_repo = _NoteDocumentRepo(documents or [])
        self.collection_repo = _CollectionRepo()
        self.document_processing_outbox_repo = _DocumentProcessingOutboxRepo()
        self.note_version_repo = _NoteVersionRepo()
        self.chunk_repo = _ChunkRepo()
        self.commits = 0

    async def __aenter__(self) -> _NoteUow:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


class _NoteDocumentRepo:
    def __init__(self, documents: list[DocumentEntity]) -> None:
        self.documents = {document.id: document for document in documents}
        self.created: list[DocumentEntity] = []

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentEntity | None:
        return self.documents.get(document_id)

    async def create(self, document: DocumentEntity) -> None:
        self.created.append(document)
        self.documents[document.id] = document

    async def update(self, document: DocumentEntity) -> None:
        self.documents[document.id] = document


class _CollectionRepo:
    async def get_by_id(self, collection_id: uuid.UUID) -> None:
        return None


class _DocumentProcessingOutboxRepo:
    def __init__(self) -> None:
        self.created: list[tuple[uuid.UUID, str]] = []
        self.dispatched: list[uuid.UUID] = []

    async def create_outbox(self, *, document_id: uuid.UUID, task_name: str) -> object:
        self.created.append((document_id, task_name))
        return _OutboxRecord(id=uuid.uuid4())

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
