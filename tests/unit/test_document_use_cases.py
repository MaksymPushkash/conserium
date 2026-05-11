import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.application.dtos.document_dtos import CreateDocumentDTO, DeleteDocumentDTO, GetDocumentDTO, ListDocumentsDTO
from src.application.dtos.ingestion_dtos import IngestDocumentDTO
from src.application.dtos.note_dtos import CreateNoteDTO, ListNotesDTO, UpdateNoteDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.create_document_use_case import CreateDocumentUseCase
from src.application.use_cases.documents.delete_document_use_case import DeleteDocumentUseCase
from src.application.use_cases.documents.get_document_use_case import GetDocumentUseCase
from src.application.use_cases.documents.ingest_document_use_case import IngestDocumentUseCase
from src.application.use_cases.documents.list_documents_use_case import ListDocumentsUseCase
from src.application.use_cases.documents.note_use_cases import CreateNoteUseCase, ListNotesUseCase, UpdateNoteUseCase
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import DocumentAccessDeniedException, DocumentNotFoundException
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.file_storage import IFileStorage
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher


class _FakeDocumentRepository:
    def __init__(self, documents: list[DocumentEntity] | None = None) -> None:
        self.documents = {document.id: document for document in documents or []}
        self.created: list[DocumentEntity] = []
        self.deleted: list[uuid.UUID] = []

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentEntity | None:
        return self.documents.get(document_id)

    async def get_by_user_id(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        document_type: DocumentType | None = None,
    ) -> list[DocumentEntity]:
        documents = [document for document in self.documents.values() if document.user_id == user_id]
        if document_type is not None:
            documents = [document for document in documents if document.type == document_type]
        return documents[offset : offset + limit]

    async def create(self, document: DocumentEntity) -> None:
        self.created.append(document)
        self.documents[document.id] = document

    async def update(self, document: DocumentEntity) -> None:
        self.documents[document.id] = document

    async def delete(self, document_id: uuid.UUID) -> None:
        self.deleted.append(document_id)
        self.documents.pop(document_id, None)

    async def exists(self, document_id: uuid.UUID) -> bool:
        return document_id in self.documents

    async def count_by_user_id(self, user_id: uuid.UUID, *, document_type: DocumentType | None = None) -> int:
        documents = [document for document in self.documents.values() if document.user_id == user_id]
        if document_type is not None:
            documents = [document for document in documents if document.type == document_type]
        return len(documents)


class _FakeUnitOfWork:
    def __init__(self, document_repo: _FakeDocumentRepository) -> None:
        self.document_repo = document_repo
        self.chunk_repo = _FakeChunkRepository()
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is not None:
            self.rolled_back = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class _FakeChunkRepository:
    def __init__(self) -> None:
        self.deleted_document_ids: list[uuid.UUID] = []

    async def delete_by_document_id(self, document_id: uuid.UUID) -> None:
        self.deleted_document_ids.append(document_id)


class _FakeFileStorage:
    def __init__(self) -> None:
        self.deleted_paths: list[str] = []

    async def save_document_file(self, *, user_id: uuid.UUID, filename: str, content: bytes) -> object:
        raise NotImplementedError

    async def read_document_file(self, path: str) -> bytes:
        raise NotImplementedError

    async def delete_document_file(self, path: str) -> None:
        self.deleted_paths.append(path)


class _FakeStatusCache:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str]] = []

    async def set_status(self, document_id: uuid.UUID, status: str, progress: int, message: str) -> None:
        self.calls.append((status, progress, message))

    async def get_status(self, document_id: uuid.UUID) -> None:
        raise NotImplementedError

    async def delete_status(self, document_id: uuid.UUID) -> None:
        raise NotImplementedError


class _FailingTaskDispatcher:
    async def dispatch_process_document(self, document_id: str) -> None:
        raise RuntimeError("broker unavailable")

    async def dispatch_embed_and_finalize_document(
        self,
        *,
        document_id: str,
        raw_text: str,
        chunks_data: list[dict[str, object]],
        expected_content_hash: str | None = None,
    ) -> None:
        raise NotImplementedError


class _SuccessfulTaskDispatcher:
    def __init__(self) -> None:
        self.processed_document_ids: list[str] = []

    async def dispatch_process_document(self, document_id: str) -> None:
        self.processed_document_ids.append(document_id)

    async def dispatch_embed_and_finalize_document(
        self,
        *,
        document_id: str,
        raw_text: str,
        chunks_data: list[dict[str, object]],
        expected_content_hash: str | None = None,
    ) -> None:
        raise NotImplementedError


def _as_uow(uow: _FakeUnitOfWork) -> IUnitOfWork:
    return cast("IUnitOfWork", uow)


def _make_document(*, user_id: uuid.UUID | None = None) -> DocumentEntity:
    return DocumentEntity(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        collection_id=None,
        title="Saved note",
        type=DocumentType.TEXT,
        status=DocumentStatus.PENDING,
        source_url=None,
        file_path=None,
        file_size_bytes=None,
        raw_content="Important text",
        summary=None,
        word_count=2,
        language="en",
        doc_embedding=None,
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=datetime.now(UTC),
        updated_at=None,
    )


async def test_create_document_use_case_creates_pending_document() -> None:
    user_id = uuid.uuid4()
    document_repo = _FakeDocumentRepository()
    uow = _FakeUnitOfWork(document_repo)
    use_case = CreateDocumentUseCase(_as_uow(uow))

    result = await use_case(
        CreateDocumentDTO(
            user_id=user_id,
            title="New note",
            type=DocumentType.TEXT,
            raw_content="Hello",
            word_count=1,
            language="en",
        )
    )

    assert result.user_id == user_id
    assert result.title == "New note"
    assert result.status == DocumentStatus.PENDING
    assert len(document_repo.created) == 1
    assert uow.committed is True


async def test_list_documents_use_case_returns_paginated_documents() -> None:
    user_id = uuid.uuid4()
    own_document = _make_document(user_id=user_id)
    other_document = _make_document()
    document_repo = _FakeDocumentRepository([own_document, other_document])
    use_case = ListDocumentsUseCase(_as_uow(_FakeUnitOfWork(document_repo)))

    result = await use_case(ListDocumentsDTO(user_id=user_id, limit=10, offset=0))

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].id == own_document.id


async def test_get_document_use_case_returns_owned_document() -> None:
    user_id = uuid.uuid4()
    document = _make_document(user_id=user_id)
    use_case = GetDocumentUseCase(_as_uow(_FakeUnitOfWork(_FakeDocumentRepository([document]))))

    result = await use_case(GetDocumentDTO(user_id=user_id, document_id=document.id))

    assert result.id == document.id


async def test_get_document_use_case_raises_for_missing_document() -> None:
    use_case = GetDocumentUseCase(_as_uow(_FakeUnitOfWork(_FakeDocumentRepository())))

    with pytest.raises(DocumentNotFoundException):
        await use_case(GetDocumentDTO(user_id=uuid.uuid4(), document_id=uuid.uuid4()))


async def test_get_document_use_case_raises_for_foreign_document() -> None:
    document = _make_document()
    use_case = GetDocumentUseCase(_as_uow(_FakeUnitOfWork(_FakeDocumentRepository([document]))))

    with pytest.raises(DocumentAccessDeniedException):
        await use_case(GetDocumentDTO(user_id=uuid.uuid4(), document_id=document.id))


async def test_delete_document_use_case_deletes_owned_document() -> None:
    user_id = uuid.uuid4()
    document = _make_document(user_id=user_id)
    document = DocumentEntity(
        id=document.id,
        user_id=document.user_id,
        collection_id=document.collection_id,
        title=document.title,
        type=document.type,
        status=document.status,
        source_url=document.source_url,
        file_path="/tmp/uploaded.bin",
        file_size_bytes=document.file_size_bytes,
        raw_content=document.raw_content,
        summary=document.summary,
        word_count=document.word_count,
        language=document.language,
        doc_embedding=None,
        is_duplicate=document.is_duplicate,
        duplicate_of_id=document.duplicate_of_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )
    document_repo = _FakeDocumentRepository([document])
    uow = _FakeUnitOfWork(document_repo)
    file_storage = _FakeFileStorage()
    use_case = DeleteDocumentUseCase(_as_uow(uow), cast("IFileStorage", file_storage))

    await use_case(DeleteDocumentDTO(user_id=user_id, document_id=document.id))

    assert document_repo.deleted == [document.id]
    assert file_storage.deleted_paths == ["/tmp/uploaded.bin"]
    assert uow.committed is True


async def test_delete_document_use_case_raises_for_foreign_document() -> None:
    document = _make_document()
    document_repo = _FakeDocumentRepository([document])
    uow = _FakeUnitOfWork(document_repo)
    file_storage = _FakeFileStorage()
    use_case = DeleteDocumentUseCase(_as_uow(uow), cast("IFileStorage", file_storage))

    with pytest.raises(DocumentAccessDeniedException):
        await use_case(DeleteDocumentDTO(user_id=uuid.uuid4(), document_id=document.id))

    assert document_repo.deleted == []
    assert file_storage.deleted_paths == []
    assert uow.committed is False


async def test_ingest_document_use_case_marks_failed_when_dispatch_fails() -> None:
    user_id = uuid.uuid4()
    document_repo = _FakeDocumentRepository()
    uow = _FakeUnitOfWork(document_repo)
    status_cache = _FakeStatusCache()
    use_case = IngestDocumentUseCase(
        _as_uow(uow),
        cast("IDocumentStatusCache", status_cache),
        cast("ITaskDispatcher", _FailingTaskDispatcher()),
    )

    with pytest.raises(RuntimeError, match="broker unavailable"):
        await use_case(
            IngestDocumentDTO(
                user_id=user_id,
                title="Queued note",
                type=DocumentType.TEXT,
                raw_content="Hello world",
            )
        )

    assert document_repo.created
    created_document = document_repo.created[0]
    assert created_document.status == DocumentStatus.FAILED
    assert status_cache.calls[-1] == ("FAILED", 0, "Failed to queue document for processing.")


async def test_create_note_use_case_creates_markdown_document_and_queues_indexing() -> None:
    user_id = uuid.uuid4()
    document_repo = _FakeDocumentRepository()
    uow = _FakeUnitOfWork(document_repo)
    status_cache = _FakeStatusCache()
    dispatcher = _SuccessfulTaskDispatcher()
    use_case = CreateNoteUseCase(
        _as_uow(uow),
        cast("IDocumentStatusCache", status_cache),
        cast("ITaskDispatcher", dispatcher),
    )

    result = await use_case(
        CreateNoteDTO(
            user_id=user_id,
            title="Asyncio",
            content="Asyncio runs cooperative tasks on one event loop.",
            language="en",
        )
    )

    assert result.title == "Asyncio"
    assert result.status == DocumentStatus.QUEUED
    assert document_repo.created[0].type == DocumentType.MARKDOWN
    assert status_cache.calls[-1] == ("QUEUED", 0, "Queued note for memory indexing.")
    assert dispatcher.processed_document_ids == [str(result.id)]


async def test_list_notes_use_case_filters_and_counts_notes_in_repository() -> None:
    user_id = uuid.uuid4()
    note = _make_document(user_id=user_id)
    upload = _make_document(user_id=user_id)
    note = DocumentEntity(
        id=note.id,
        user_id=note.user_id,
        collection_id=note.collection_id,
        title=note.title,
        type=DocumentType.MARKDOWN,
        status=note.status,
        source_url=note.source_url,
        file_path=note.file_path,
        file_size_bytes=note.file_size_bytes,
        raw_content=note.raw_content,
        summary=note.summary,
        word_count=note.word_count,
        language=note.language,
        doc_embedding=None,
        is_duplicate=note.is_duplicate,
        duplicate_of_id=note.duplicate_of_id,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )
    document_repo = _FakeDocumentRepository([upload, note])
    use_case = ListNotesUseCase(_as_uow(_FakeUnitOfWork(document_repo)))

    result = await use_case(ListNotesDTO(user_id=user_id, limit=10, offset=0))

    assert result.total == 1
    assert [item.id for item in result.items] == [note.id]


async def test_update_note_use_case_clears_chunks_for_empty_note() -> None:
    user_id = uuid.uuid4()
    base_note = _make_document(user_id=user_id)
    note = DocumentEntity(
        id=base_note.id,
        user_id=base_note.user_id,
        collection_id=base_note.collection_id,
        title=base_note.title,
        type=DocumentType.MARKDOWN,
        status=base_note.status,
        source_url=base_note.source_url,
        file_path=base_note.file_path,
        file_size_bytes=base_note.file_size_bytes,
        raw_content=base_note.raw_content,
        summary=base_note.summary,
        word_count=base_note.word_count,
        language=base_note.language,
        doc_embedding=None,
        is_duplicate=base_note.is_duplicate,
        duplicate_of_id=base_note.duplicate_of_id,
        created_at=base_note.created_at,
        updated_at=base_note.updated_at,
    )
    document_repo = _FakeDocumentRepository([note])
    uow = _FakeUnitOfWork(document_repo)
    status_cache = _FakeStatusCache()
    dispatcher = _SuccessfulTaskDispatcher()
    use_case = UpdateNoteUseCase(
        _as_uow(uow),
        cast("IDocumentStatusCache", status_cache),
        cast("ITaskDispatcher", dispatcher),
    )

    result = await use_case(UpdateNoteDTO(user_id=user_id, note_id=note.id, title="Empty", content=""))

    assert result.status == DocumentStatus.READY
    assert uow.chunk_repo.deleted_document_ids == [note.id]
    assert dispatcher.processed_document_ids == []
