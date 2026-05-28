import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.application.dtos.document_dtos import (
    CreateDocumentDTO,
    DeleteDocumentDTO,
    GetDocumentDTO,
    ListDocumentsDTO,
    SearchDocumentsDTO,
)
from src.application.dtos.ingestion_dtos import IngestDocumentDTO
from src.application.dtos.note_dtos import CreateNoteDTO, GetNoteDTO, ListNotesDTO, UpdateNoteDTO
from src.application.ports.ai.embedding_provider import IEmbeddingProvider
from src.application.ports.persistence.chunk_repository import ChunkSearchResult
from src.application.ports.persistence.document_activity_repository import (
    DocumentActivityEventType,
    DocumentActivitySummary,
)
from src.application.ports.persistence.document_repository import RelatedDocumentRecord
from src.application.ports.persistence.note_version_repository import NoteVersionRecord
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.create_document_use_case import CreateDocumentUseCase
from src.application.use_cases.documents.delete_document_use_case import DeleteDocumentUseCase
from src.application.use_cases.documents.get_document_connections_use_case import GetDocumentConnectionsUseCase
from src.application.use_cases.documents.get_document_use_case import GetDocumentUseCase
from src.application.use_cases.documents.ingest_document_use_case import IngestDocumentUseCase
from src.application.use_cases.documents.list_documents_use_case import ListDocumentsUseCase
from src.application.use_cases.documents.note_use_cases import (
    CreateNoteUseCase,
    DeleteNoteUseCase,
    GetNoteUseCase,
    ListNotesUseCase,
    ListNoteVersionsUseCase,
    RestoreNoteVersionUseCase,
    UpdateNoteUseCase,
)
from src.application.use_cases.documents.search_documents_use_case import SearchDocumentsUseCase
from src.domain.entities.chunk_entity import ChunkEntity
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
        collection_id: uuid.UUID | None = None,
        status: DocumentStatus | None = None,
    ) -> list[DocumentEntity]:
        documents = [document for document in self.documents.values() if document.user_id == user_id]
        if document_type is not None:
            documents = [document for document in documents if document.type == document_type]
        if collection_id is not None:
            documents = [document for document in documents if document.collection_id == collection_id]
        if status is not None:
            documents = [document for document in documents if document.status == status]
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

    async def count_by_user_id(
        self,
        user_id: uuid.UUID,
        *,
        document_type: DocumentType | None = None,
        collection_id: uuid.UUID | None = None,
        status: DocumentStatus | None = None,
    ) -> int:
        documents = [document for document in self.documents.values() if document.user_id == user_id]
        if document_type is not None:
            documents = [document for document in documents if document.type == document_type]
        if collection_id is not None:
            documents = [document for document in documents if document.collection_id == collection_id]
        if status is not None:
            documents = [document for document in documents if document.status == status]
        return len(documents)

    async def get_related_documents(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        limit: int = 5,
    ) -> list[RelatedDocumentRecord]:
        target = self.documents.get(document_id)
        if target is None or target.user_id != user_id:
            return []
        records: list[RelatedDocumentRecord] = []
        target_tags = set(target.tags)
        for document in self.documents.values():
            if document.id == document_id or document.user_id != user_id:
                continue
            shared_tags = sorted(target_tags.intersection(document.tags))
            if not shared_tags:
                continue
            records.append(
                RelatedDocumentRecord(
                    document=document,
                    reasons=[f"Shared tags: {', '.join(shared_tags)}"],
                    relationship_score=len(shared_tags) * 3,
                )
            )
        return records[:limit]


class _FakeUnitOfWork:
    def __init__(self, document_repo: _FakeDocumentRepository) -> None:
        self.document_repo = document_repo
        self.document_activity_repo = _FakeDocumentActivityRepository()
        self.document_processing_outbox_repo = _FakeDocumentProcessingOutboxRepository()
        self.chunk_repo = _FakeChunkRepository()
        self.note_version_repo = _FakeNoteVersionRepository()
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


class _FakeDocumentActivityRepository:
    def __init__(self) -> None:
        self.events: list[tuple[uuid.UUID, uuid.UUID, DocumentActivityEventType]] = []
        self.summaries: dict[uuid.UUID, DocumentActivitySummary] = {}

    async def record_event(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        event_type: DocumentActivityEventType,
    ) -> None:
        self.events.append((user_id, document_id, event_type))

    async def summarize_by_document_ids(
        self,
        *,
        user_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, DocumentActivitySummary]:
        return {document_id: self.summaries[document_id] for document_id in document_ids if document_id in self.summaries}


class _FakeDocumentProcessingOutboxRepository:
    def __init__(self, *, fail_create: bool = False) -> None:
        self.created: list[tuple[uuid.UUID, str]] = []
        self.dispatched: list[uuid.UUID] = []
        self.fail_create = fail_create

    async def create_outbox(self, *, document_id: uuid.UUID, task_name: str) -> object:
        if self.fail_create:
            raise RuntimeError("outbox unavailable")
        self.created.append((document_id, task_name))
        return _OutboxRecord(id=uuid.uuid4())

    async def mark_dispatched(self, outbox_id: uuid.UUID, dispatched_at: object) -> object:
        self.dispatched.append(outbox_id)
        return _OutboxRecord(id=outbox_id)


@dataclass(frozen=True, slots=True)
class _OutboxRecord:
    id: uuid.UUID


class _FakeChunkRepository:
    def __init__(self) -> None:
        self.deleted_document_ids: list[uuid.UUID] = []
        self.search_results: list[ChunkSearchResult] = []
        self.search_calls: list[dict[str, object]] = []

    async def delete_by_document_id(self, document_id: uuid.UUID) -> None:
        self.deleted_document_ids.append(document_id)

    async def hybrid_search(
        self,
        *,
        query: str,
        embedding: list[float],
        user_id: uuid.UUID,
        limit: int = 10,
        collection_id: uuid.UUID | None = None,
        tag_names: tuple[str, ...] | None = None,
        document_types: tuple[DocumentType, ...] | None = None,
        document_ids: tuple[uuid.UUID, ...] | None = None,
    ) -> list[ChunkSearchResult]:
        self.search_calls.append(
            {
                "query": query,
                "embedding": embedding,
                "user_id": user_id,
                "limit": limit,
                "collection_id": collection_id,
                "tag_names": tag_names,
                "document_types": document_types,
                "document_ids": document_ids,
            }
        )
        return self.search_results


class _FakeEmbeddingProvider(IEmbeddingProvider):
    async def embed_text(self, text: str) -> list[float]:
        return [0.1] * ChunkEntity.EMBEDDING_DIMENSIONS

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * ChunkEntity.EMBEDDING_DIMENSIONS for _ in texts]


class _FakeNoteVersionRepository:
    def __init__(self) -> None:
        self.records: list[NoteVersionRecord] = []

    async def create(self, version: NoteVersionRecord) -> None:
        self.records.append(replace(version, created_at=datetime.now(UTC)))

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
        return sum(1 for record in self.records if record.note_id == note_id)


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


class _FailingStatusCache(_FakeStatusCache):
    async def set_status(self, document_id: uuid.UUID, status: str, progress: int, message: str) -> None:
        raise RuntimeError("cache unavailable")


class _FailingTaskDispatcher:
    async def dispatch_process_document(self, document_id: str, *, task_id: str | None = None) -> None:
        raise RuntimeError("broker unavailable")

    async def dispatch_process_image_document(self, document_id: str) -> None:
        raise NotImplementedError

    async def dispatch_repo_sync_outbox(self) -> None:
        raise NotImplementedError

    async def dispatch_document_processing_outbox(self) -> None:
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
        self.document_processing_outbox_dispatches = 0

    async def dispatch_process_document(self, document_id: str, *, task_id: str | None = None) -> None:
        self.processed_document_ids.append(document_id)

    async def dispatch_process_image_document(self, document_id: str) -> None:
        raise NotImplementedError

    async def dispatch_repo_sync_outbox(self) -> None:
        raise NotImplementedError

    async def dispatch_document_processing_outbox(self) -> None:
        self.document_processing_outbox_dispatches += 1

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


def _make_document(
    *,
    user_id: uuid.UUID | None = None,
    title: str = "Saved note",
    status: DocumentStatus = DocumentStatus.PENDING,
    tags: list[str] | None = None,
) -> DocumentEntity:
    return DocumentEntity(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        collection_id=None,
        title=title,
        type=DocumentType.TEXT,
        status=status,
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
        tags=tags,
    )


def _make_note_document(
    *,
    user_id: uuid.UUID | None = None,
    title: str = "Saved note",
    content: str = "Important text",
    status: DocumentStatus = DocumentStatus.READY,
) -> DocumentEntity:
    document = _make_document(user_id=user_id, title=title, status=status)
    return DocumentEntity(
        id=document.id,
        user_id=document.user_id,
        collection_id=document.collection_id,
        title=document.title,
        type=DocumentType.MARKDOWN,
        status=document.status,
        source_url=document.source_url,
        file_path=document.file_path,
        file_size_bytes=document.file_size_bytes,
        raw_content=content,
        summary=document.summary,
        word_count=len(content.split()),
        language=document.language,
        doc_embedding=None,
        is_duplicate=document.is_duplicate,
        duplicate_of_id=document.duplicate_of_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _make_chunk(document_id: uuid.UUID, content: str) -> ChunkEntity:
    return ChunkEntity.create(
        id=uuid.uuid4(),
        document_id=document_id,
        content=content,
        embedding=[0.1] * ChunkEntity.EMBEDDING_DIMENSIONS,
        chunk_index=0,
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


async def test_search_documents_use_case_returns_document_results_from_hybrid_chunks() -> None:
    user_id = uuid.uuid4()
    document = _make_document(user_id=user_id, title="Async Python", status=DocumentStatus.READY)
    document_repo = _FakeDocumentRepository([document])
    uow = _FakeUnitOfWork(document_repo)
    chunk = _make_chunk(document.id, "asyncio schedules coroutines for concurrent I/O.")
    uow.chunk_repo.search_results = [ChunkSearchResult(chunk=chunk, document_title=document.title, score=0.91)]
    use_case = SearchDocumentsUseCase(_as_uow(uow), _FakeEmbeddingProvider())

    result = await use_case(SearchDocumentsDTO(user_id=user_id, query="parallel requests", limit=10))

    assert result.total == 1
    assert result.items[0].document.id == document.id
    assert result.items[0].snippet == "asyncio schedules coroutines for concurrent I/O."
    assert result.items[0].score == 0.91
    assert uow.chunk_repo.search_calls[0]["query"] == "parallel requests"


async def test_search_documents_use_case_filters_document_status_after_chunk_search() -> None:
    user_id = uuid.uuid4()
    ready_document = _make_document(user_id=user_id, title="Ready", status=DocumentStatus.READY)
    failed_document = _make_document(user_id=user_id, title="Failed", status=DocumentStatus.FAILED)
    document_repo = _FakeDocumentRepository([ready_document, failed_document])
    uow = _FakeUnitOfWork(document_repo)
    uow.chunk_repo.search_results = [
        ChunkSearchResult(chunk=_make_chunk(failed_document.id, "failed document content"), document_title=failed_document.title, score=0.95),
        ChunkSearchResult(chunk=_make_chunk(ready_document.id, "ready document content"), document_title=ready_document.title, score=0.9),
    ]
    use_case = SearchDocumentsUseCase(_as_uow(uow), _FakeEmbeddingProvider())

    result = await use_case(SearchDocumentsDTO(user_id=user_id, query="document", limit=10, status=DocumentStatus.READY))

    assert [item.document.id for item in result.items] == [ready_document.id]


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


async def test_get_document_connections_returns_related_documents_with_activity() -> None:
    user_id = uuid.uuid4()
    target = _make_document(user_id=user_id, title="Python asyncio", tags=["python", "asyncio"])
    related = _make_document(user_id=user_id, title="Asyncio gather", status=DocumentStatus.READY, tags=["asyncio"])
    unrelated = _make_document(user_id=user_id, title="Cooking", status=DocumentStatus.READY, tags=["food"])
    uow = _FakeUnitOfWork(_FakeDocumentRepository([target, related, unrelated]))
    uow.document_activity_repo.summaries[related.id] = DocumentActivitySummary(
        document_id=related.id,
        last_used_at=datetime.now(UTC),
        query_count=3,
        citation_count=1,
    )
    use_case = GetDocumentConnectionsUseCase(_as_uow(uow))

    result = await use_case(GetDocumentDTO(user_id=user_id, document_id=target.id), limit=5)

    assert result.total == 1
    assert result.items[0].document.id == related.id
    assert result.items[0].reasons == ["Shared tags: asyncio"]
    assert result.items[0].document.query_count == 3


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


async def test_ingest_document_use_case_persists_outbox_when_drainer_dispatch_fails() -> None:
    user_id = uuid.uuid4()
    document_repo = _FakeDocumentRepository()
    uow = _FakeUnitOfWork(document_repo)
    status_cache = _FakeStatusCache()
    use_case = IngestDocumentUseCase(
        _as_uow(uow),
        cast("IDocumentStatusCache", status_cache),
        cast("ITaskDispatcher", _FailingTaskDispatcher()),
    )

    result = await use_case(
        IngestDocumentDTO(
            user_id=user_id,
            title="Queued note",
            type=DocumentType.TEXT,
            raw_content="Hello world",
        )
    )

    assert document_repo.created
    created_document = document_repo.created[0]
    assert result.status == DocumentStatus.FAILED
    assert created_document.status == DocumentStatus.FAILED
    assert uow.document_processing_outbox_repo.created == [(created_document.id, "process_document")]
    assert status_cache.calls[-1] == ("FAILED", 0, "Document processing dispatch failed. Retry processing from the document actions.")


async def test_ingest_document_use_case_persists_outbox_when_status_cache_fails() -> None:
    user_id = uuid.uuid4()
    document_repo = _FakeDocumentRepository()
    uow = _FakeUnitOfWork(document_repo)
    dispatcher = _SuccessfulTaskDispatcher()
    use_case = IngestDocumentUseCase(
        _as_uow(uow),
        cast("IDocumentStatusCache", _FailingStatusCache()),
        cast("ITaskDispatcher", dispatcher),
    )

    result = await use_case(
        IngestDocumentDTO(
            user_id=user_id,
            title="Queued note",
            type=DocumentType.TEXT,
            raw_content="Hello world",
        )
    )

    assert document_repo.created
    assert result.status == DocumentStatus.QUEUED
    assert document_repo.created[0].status == DocumentStatus.QUEUED
    assert uow.document_processing_outbox_repo.created == [(document_repo.created[0].id, "process_document")]
    assert dispatcher.processed_document_ids == []
    assert dispatcher.document_processing_outbox_dispatches == 1


async def test_ingest_document_use_case_falls_back_to_direct_dispatch_when_outbox_create_fails() -> None:
    user_id = uuid.uuid4()
    document_repo = _FakeDocumentRepository()
    uow = _FakeUnitOfWork(document_repo)
    uow.document_processing_outbox_repo = _FakeDocumentProcessingOutboxRepository(fail_create=True)
    status_cache = _FakeStatusCache()
    dispatcher = _SuccessfulTaskDispatcher()
    use_case = IngestDocumentUseCase(
        _as_uow(uow),
        cast("IDocumentStatusCache", status_cache),
        cast("ITaskDispatcher", dispatcher),
    )

    result = await use_case(
        IngestDocumentDTO(
            user_id=user_id,
            title="Fallback note",
            type=DocumentType.TEXT,
            raw_content="Hello world",
        )
    )

    assert document_repo.created
    created_document = document_repo.created[0]
    assert result.status == DocumentStatus.QUEUED
    assert created_document.status == DocumentStatus.QUEUED
    assert status_cache.calls[-1] == ("QUEUED", 0, "Queued for processing.")
    assert dispatcher.processed_document_ids == [str(created_document.id)]


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
    assert uow.document_processing_outbox_repo.created == [(result.id, "process_document")]
    assert dispatcher.processed_document_ids == []
    assert dispatcher.document_processing_outbox_dispatches == 1


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


async def test_get_note_use_case_returns_owned_note() -> None:
    user_id = uuid.uuid4()
    note = _make_note_document(user_id=user_id)
    use_case = GetNoteUseCase(_as_uow(_FakeUnitOfWork(_FakeDocumentRepository([note]))))

    result = await use_case(GetNoteDTO(user_id=user_id, note_id=note.id))

    assert result.id == note.id
    assert result.content == "Important text"


async def test_delete_note_use_case_deletes_owned_note() -> None:
    user_id = uuid.uuid4()
    note = _make_note_document(user_id=user_id)
    document_repo = _FakeDocumentRepository([note])
    uow = _FakeUnitOfWork(document_repo)
    use_case = DeleteNoteUseCase(_as_uow(uow))

    await use_case(user_id=user_id, note_id=note.id)

    assert document_repo.deleted == [note.id]
    assert uow.committed is True


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
    assert dispatcher.document_processing_outbox_dispatches == 0


async def test_update_note_use_case_does_not_version_noop_update() -> None:
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
    uow = _FakeUnitOfWork(_FakeDocumentRepository([note]))
    use_case = UpdateNoteUseCase(
        _as_uow(uow),
        cast("IDocumentStatusCache", _FakeStatusCache()),
        cast("ITaskDispatcher", _SuccessfulTaskDispatcher()),
    )

    await use_case(UpdateNoteDTO(user_id=user_id, note_id=note.id, title=note.title, content=note.raw_content or ""))

    assert uow.note_version_repo.records == []


async def test_update_note_use_case_coalesces_autosave_versions() -> None:
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
    uow = _FakeUnitOfWork(_FakeDocumentRepository([note]))
    use_case = UpdateNoteUseCase(
        _as_uow(uow),
        cast("IDocumentStatusCache", _FakeStatusCache()),
        cast("ITaskDispatcher", _SuccessfulTaskDispatcher()),
    )

    await use_case(UpdateNoteDTO(user_id=user_id, note_id=note.id, title=note.title, content="First autosave"))
    await use_case(UpdateNoteDTO(user_id=user_id, note_id=note.id, title=note.title, content="Second autosave"))

    assert len(uow.note_version_repo.records) == 1


async def test_list_note_versions_use_case_returns_owned_note_versions() -> None:
    user_id = uuid.uuid4()
    note = _make_note_document(user_id=user_id)
    uow = _FakeUnitOfWork(_FakeDocumentRepository([note]))
    version_id = uuid.uuid4()
    uow.note_version_repo.records.append(
        NoteVersionRecord(
            id=version_id,
            note_id=note.id,
            user_id=user_id,
            version_number=1,
            title="Earlier note",
            content="Earlier content",
            created_at=datetime.now(UTC),
        )
    )
    use_case = ListNoteVersionsUseCase(_as_uow(uow))

    result = await use_case(user_id=user_id, note_id=note.id)

    assert [version.id for version in result] == [version_id]
    assert result[0].content == "Earlier content"


async def test_restore_note_version_use_case_restores_content_and_queues_processing() -> None:
    user_id = uuid.uuid4()
    note = _make_note_document(user_id=user_id, title="Current", content="Current content")
    uow = _FakeUnitOfWork(_FakeDocumentRepository([note]))
    version_id = uuid.uuid4()
    uow.note_version_repo.records.append(
        NoteVersionRecord(
            id=version_id,
            note_id=note.id,
            user_id=user_id,
            version_number=1,
            title="Restored",
            content="Restored content",
            created_at=datetime.now(UTC),
        )
    )
    status_cache = _FakeStatusCache()
    dispatcher = _SuccessfulTaskDispatcher()
    use_case = RestoreNoteVersionUseCase(
        _as_uow(uow),
        cast("IDocumentStatusCache", status_cache),
        cast("ITaskDispatcher", dispatcher),
    )

    result = await use_case(user_id=user_id, note_id=note.id, version_id=version_id)

    assert result.title == "Restored"
    assert result.content == "Restored content"
    assert result.status == DocumentStatus.QUEUED
    assert len(uow.note_version_repo.records) == 2
    assert uow.document_processing_outbox_repo.created == [(note.id, "process_document")]
    assert dispatcher.processed_document_ids == []
    assert dispatcher.document_processing_outbox_dispatches == 1
