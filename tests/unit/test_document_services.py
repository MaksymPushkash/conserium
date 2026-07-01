import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.documents.document_repository import DocumentRepository
from src.documents.ingestion import DocumentIngester
from src.documents.notes import (
    NoteService,
)
from src.documents.processing import DocumentProcessingService
from src.documents.repository import (
    ChunkSearchResult,
    DocumentActivityEventType,
    DocumentActivitySummary,
    NoteVersionRecord,
    RelatedDocumentRecord,
)
from src.documents.schemas import (
    CreateDocumentRequest,
    CreateNoteRequest,
    UpdateNoteRequest,
)
from src.documents.service import (
    DocumentService,
)
from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.kit.ai.embedding_provider import EmbeddingProvider
from src.kit.exceptions import DocumentAccessDeniedException, DocumentNotFoundException
from src.kit.storage.file_storage import FileStorage
from src.models.chunk import ChunkModel
from src.models.document import DocumentModel

if TYPE_CHECKING:
    from src.documents.access import DocumentCollectionAccess
    from src.documents.status_cache import RedisDocumentStatusCache
    from src.query.repository import SearchQueryRepository
    from src.worker.dispatcher import TaskiqTaskDispatcher


class _FakeDocumentRepository:
    def __init__(self, documents: list[DocumentModel] | None = None) -> None:
        self.documents = {document.id: document for document in documents or []}
        self.created: list[DocumentModel] = []
        self.deleted: list[uuid.UUID] = []

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentModel | None:
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
        tag_name: str | None = None,
    ) -> list[DocumentModel]:
        documents = [document for document in self.documents.values() if document.user_id == user_id]
        if document_type is not None:
            documents = [document for document in documents if document.type == document_type]
        if collection_id is not None:
            documents = [document for document in documents if document.collection_id == collection_id]
        if status is not None:
            documents = [document for document in documents if document.status == status]
        if tag_name is not None:
            documents = [document for document in documents if tag_name in (document.tags or [])]
        return documents[offset : offset + limit]

    async def create(self, document: DocumentModel) -> None:
        self.created.append(document)
        self.documents[document.id] = document

    async def update(self, document: DocumentModel) -> None:
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
        tag_name: str | None = None,
    ) -> int:
        documents = [document for document in self.documents.values() if document.user_id == user_id]
        if document_type is not None:
            documents = [document for document in documents if document.type == document_type]
        if collection_id is not None:
            documents = [document for document in documents if document.collection_id == collection_id]
        if status is not None:
            documents = [document for document in documents if document.status == status]
        if tag_name is not None:
            documents = [document for document in documents if tag_name in (document.tags or [])]
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


class _FakeRepositorySession:
    def __init__(self, document_repo: _FakeDocumentRepository) -> None:
        self.document_repo = document_repo
        self.collection_repo = _FakeCollectionRepository()
        self.shared_workspace_repo = _FakeSharedWorkspaceRepository()
        self.document_activity_repo = _FakeDocumentActivityRepository()
        self.document_processing_outbox_repo = _FakeDocumentProcessingOutboxRepository()
        self.chunk_repo = _FakeChunkRepository()
        self.note_version_repo = _FakeNoteVersionRepository()
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> "_FakeRepositorySession":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is not None:
            self.rolled_back = True

    async def commit(self) -> None:
        self.committed = True

    async def flush(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class _FakeSharedWorkspaceRepository:
    async def create_audit_event(self, **kwargs: object) -> None:
        return None


class _FakeCollectionRepository:
    async def get_by_id(self, collection_id: uuid.UUID) -> None:
        return None


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

    async def mark_dispatching(self, outbox_id: uuid.UUID, locked_at: object) -> object:
        return _OutboxRecord(id=outbox_id)

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


class _FakeEmbeddingProvider(EmbeddingProvider):
    async def embed_text(self, text: str) -> list[float]:
        return [0.1] * ChunkModel.EMBEDDING_DIMENSIONS

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * ChunkModel.EMBEDDING_DIMENSIONS for _ in texts]


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


def _as_document_repository(repository_session: _FakeRepositorySession) -> DocumentRepository:
    return cast("DocumentRepository", repository_session.document_repo)


def _processing_service(
    repository_session: _FakeRepositorySession,
    status_cache: _FakeStatusCache,
    task_dispatcher: _FailingTaskDispatcher | _SuccessfulTaskDispatcher,
) -> DocumentProcessingService:
    return DocumentProcessingService(
        repository_session,  # type: ignore[arg-type]
        repository_session.document_repo,  # type: ignore[arg-type]
        repository_session.document_processing_outbox_repo,  # type: ignore[arg-type]
        cast("RedisDocumentStatusCache", status_cache),
        cast("TaskiqTaskDispatcher", task_dispatcher),
    )


def _document_service(
    repository_session: _FakeRepositorySession,
    *,
    embedding_provider: EmbeddingProvider | None = None,
    file_storage: FileStorage | None = None,
) -> DocumentService:
    status_cache = _FakeStatusCache()
    dispatcher = _SuccessfulTaskDispatcher()
    return DocumentService(
        repository_session,  # type: ignore[arg-type]
        _as_document_repository(repository_session),
        cast("DocumentCollectionAccess", repository_session),
        repository_session.document_activity_repo,
        embedding_provider or _FakeEmbeddingProvider(),
        repository_session.chunk_repo,
        cast("SearchQueryRepository", object()),
        file_storage or cast("FileStorage", _FakeFileStorage()),
        _processing_service(repository_session, status_cache, dispatcher),
    )


def _note_service(
    repository_session: _FakeRepositorySession,
    *,
    status_cache: _FakeStatusCache | None = None,
    dispatcher: _SuccessfulTaskDispatcher | None = None,
) -> NoteService:
    cache = status_cache or _FakeStatusCache()
    task_dispatcher = dispatcher or _SuccessfulTaskDispatcher()
    return NoteService(
        repository_session,  # type: ignore[arg-type]
        _as_document_repository(repository_session),
        cast("DocumentCollectionAccess", repository_session),
        repository_session.note_version_repo,
        _processing_service(repository_session, cache, task_dispatcher),
        repository_session.chunk_repo,
    )


def _make_document(
    *,
    user_id: uuid.UUID | None = None,
    title: str = "Saved note",
    status: DocumentStatus = DocumentStatus.PENDING,
    tags: list[str] | None = None,
) -> DocumentModel:
    return DocumentModel(
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
) -> DocumentModel:
    document = _make_document(user_id=user_id, title=title, status=status)
    return DocumentModel(
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


def _make_chunk(document_id: uuid.UUID, content: str) -> ChunkModel:
    return ChunkModel.create(
        id=uuid.uuid4(),
        document_id=document_id,
        content=content,
        embedding=[0.1] * ChunkModel.EMBEDDING_DIMENSIONS,
        chunk_index=0,
    )


async def test_create_document_service_creates_pending_document() -> None:
    user_id = uuid.uuid4()
    document_repo = _FakeDocumentRepository()
    repository_session = _FakeRepositorySession(document_repo)
    service = _document_service(repository_session)

    result = await service.create(
        user_id=user_id,
        body=CreateDocumentRequest(
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
    assert repository_session.committed is True


async def test_list_documents_service_returns_paginated_documents() -> None:
    user_id = uuid.uuid4()
    own_document = _make_document(user_id=user_id)
    other_document = _make_document()
    document_repo = _FakeDocumentRepository([own_document, other_document])
    repository_session = _FakeRepositorySession(document_repo)
    service = _document_service(repository_session)

    result = await service.list(user_id=user_id, limit=10, offset=0)

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].id == own_document.id


async def test_list_documents_service_filters_by_type_and_tag() -> None:
    user_id = uuid.uuid4()
    matching_document = _make_document(user_id=user_id, tags=["python"])
    other_document = _make_document(user_id=user_id, tags=["typescript"])
    document_repo = _FakeDocumentRepository([matching_document, other_document])
    repository_session = _FakeRepositorySession(document_repo)
    service = _document_service(repository_session)

    result = await service.list(
        user_id=user_id,
        limit=10,
        offset=0,
        document_type=DocumentType.TEXT,
        tag_name="python",
    )

    assert result.total == 1
    assert [document.id for document in result.items] == [matching_document.id]


async def test_search_documents_service_returns_document_results_from_hybrid_chunks() -> None:
    user_id = uuid.uuid4()
    document = _make_document(user_id=user_id, title="Async Python", status=DocumentStatus.READY)
    document_repo = _FakeDocumentRepository([document])
    repository_session = _FakeRepositorySession(document_repo)
    chunk = _make_chunk(document.id, "asyncio schedules coroutines for concurrent I/O.")
    repository_session.chunk_repo.search_results = [ChunkSearchResult(chunk=chunk, document_title=document.title, score=0.91)]
    service = _document_service(repository_session)

    result = await service.search(user_id=user_id, query="parallel requests", limit=10)

    assert result.total == 1
    assert result.items[0].document.id == document.id
    assert result.items[0].snippet == "asyncio schedules coroutines for concurrent I/O."
    assert result.items[0].score == 0.91
    assert repository_session.chunk_repo.search_calls[0]["query"] == "parallel requests"


async def test_search_documents_service_filters_document_status_after_chunk_search() -> None:
    user_id = uuid.uuid4()
    ready_document = _make_document(user_id=user_id, title="Ready", status=DocumentStatus.READY)
    failed_document = _make_document(user_id=user_id, title="Failed", status=DocumentStatus.FAILED)
    document_repo = _FakeDocumentRepository([ready_document, failed_document])
    repository_session = _FakeRepositorySession(document_repo)
    repository_session.chunk_repo.search_results = [
        ChunkSearchResult(chunk=_make_chunk(failed_document.id, "failed document content"), document_title=failed_document.title, score=0.95),
        ChunkSearchResult(chunk=_make_chunk(ready_document.id, "ready document content"), document_title=ready_document.title, score=0.9),
    ]
    service = _document_service(repository_session)

    result = await service.search(user_id=user_id, query="document", limit=10, status=DocumentStatus.READY)

    assert [item.document.id for item in result.items] == [ready_document.id]


async def test_get_document_service_returns_owned_document() -> None:
    user_id = uuid.uuid4()
    document = _make_document(user_id=user_id)
    repository_session = _FakeRepositorySession(_FakeDocumentRepository([document]))
    service = _document_service(repository_session)

    result = await service.get(user_id=user_id, document_id=document.id)

    assert result.id == document.id


async def test_get_document_service_raises_for_missing_document() -> None:
    repository_session = _FakeRepositorySession(_FakeDocumentRepository())
    service = _document_service(repository_session)

    with pytest.raises(DocumentNotFoundException):
        await service.get(user_id=uuid.uuid4(), document_id=uuid.uuid4())


async def test_get_document_service_raises_for_foreign_document() -> None:
    document = _make_document()
    repository_session = _FakeRepositorySession(_FakeDocumentRepository([document]))
    service = _document_service(repository_session)

    with pytest.raises(DocumentAccessDeniedException):
        await service.get(user_id=uuid.uuid4(), document_id=document.id)


async def test_get_document_connections_returns_related_documents_with_activity() -> None:
    user_id = uuid.uuid4()
    target = _make_document(user_id=user_id, title="Python asyncio", tags=["python", "asyncio"])
    related = _make_document(user_id=user_id, title="Asyncio gather", status=DocumentStatus.READY, tags=["asyncio"])
    unrelated = _make_document(user_id=user_id, title="Cooking", status=DocumentStatus.READY, tags=["food"])
    repository_session = _FakeRepositorySession(_FakeDocumentRepository([target, related, unrelated]))
    repository_session.document_activity_repo.summaries[related.id] = DocumentActivitySummary(
        document_id=related.id,
        last_used_at=datetime.now(UTC),
        query_count=3,
        citation_count=1,
    )
    service = _document_service(repository_session)

    result = await service.connections(user_id=user_id, document_id=target.id, limit=5)

    assert result.total == 1
    assert result.items[0].document.id == related.id
    assert result.items[0].reasons == ["Shared tags: asyncio"]
    assert result.items[0].document.query_count == 3


async def test_delete_document_service_deletes_owned_document() -> None:
    user_id = uuid.uuid4()
    document = _make_document(user_id=user_id)
    document = DocumentModel(
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
    repository_session = _FakeRepositorySession(document_repo)
    file_storage = _FakeFileStorage()
    service = _document_service(repository_session, file_storage=cast("FileStorage", file_storage))

    await service.delete(user_id=user_id, document_id=document.id)

    assert document_repo.deleted == [document.id]
    assert file_storage.deleted_paths == ["/tmp/uploaded.bin"]
    assert repository_session.committed is True


async def test_delete_document_service_raises_for_foreign_document() -> None:
    document = _make_document()
    document_repo = _FakeDocumentRepository([document])
    repository_session = _FakeRepositorySession(document_repo)
    file_storage = _FakeFileStorage()
    service = _document_service(repository_session, file_storage=cast("FileStorage", file_storage))

    with pytest.raises(DocumentAccessDeniedException):
        await service.delete(user_id=uuid.uuid4(), document_id=document.id)

    assert document_repo.deleted == []
    assert file_storage.deleted_paths == []
    assert repository_session.committed is False


async def test_ingest_document_service_queues_outbox_without_dispatching_in_request() -> None:
    user_id = uuid.uuid4()
    document_repo = _FakeDocumentRepository()
    repository_session = _FakeRepositorySession(document_repo)
    status_cache = _FakeStatusCache()
    dispatcher = _FailingTaskDispatcher()
    handler = DocumentIngester(
        repository_session,  # type: ignore[arg-type]
        _as_document_repository(repository_session),
        cast("RedisDocumentStatusCache", status_cache),
        cast("TaskiqTaskDispatcher", dispatcher),
        repository_session,
        repository_session.document_activity_repo,
        _processing_service(repository_session, status_cache, dispatcher),
    )

    result = await handler(
        user_id=user_id,
        title="Queued note",
        type=DocumentType.TEXT,
        raw_content="Hello world",
    )

    assert document_repo.created
    created_document = document_repo.created[0]
    assert result.status == DocumentStatus.QUEUED
    assert created_document.status == DocumentStatus.QUEUED
    assert repository_session.document_processing_outbox_repo.created == [(created_document.id, "process_document")]
    assert status_cache.calls[-1] == ("QUEUED", 0, "Queued for processing.")


async def test_ingest_document_service_persists_outbox_when_status_cache_fails() -> None:
    user_id = uuid.uuid4()
    document_repo = _FakeDocumentRepository()
    repository_session = _FakeRepositorySession(document_repo)
    dispatcher = _SuccessfulTaskDispatcher()
    status_cache = _FailingStatusCache()
    handler = DocumentIngester(
        repository_session,  # type: ignore[arg-type]
        _as_document_repository(repository_session),
        cast("RedisDocumentStatusCache", status_cache),
        cast("TaskiqTaskDispatcher", dispatcher),
        repository_session,
        repository_session.document_activity_repo,
        _processing_service(repository_session, status_cache, dispatcher),
    )

    result = await handler(
        user_id=user_id,
        title="Queued note",
        type=DocumentType.TEXT,
        raw_content="Hello world",
    )

    assert document_repo.created
    assert result.status == DocumentStatus.QUEUED
    assert document_repo.created[0].status == DocumentStatus.QUEUED
    assert repository_session.document_processing_outbox_repo.created == [(document_repo.created[0].id, "process_document")]
    assert dispatcher.processed_document_ids == []
    assert dispatcher.document_processing_outbox_dispatches == 0


async def test_ingest_document_service_fails_transaction_when_outbox_create_fails() -> None:
    user_id = uuid.uuid4()
    document_repo = _FakeDocumentRepository()
    repository_session = _FakeRepositorySession(document_repo)
    repository_session.document_processing_outbox_repo = _FakeDocumentProcessingOutboxRepository(fail_create=True)
    status_cache = _FakeStatusCache()
    dispatcher = _SuccessfulTaskDispatcher()
    handler = DocumentIngester(
        repository_session,  # type: ignore[arg-type]
        _as_document_repository(repository_session),
        cast("RedisDocumentStatusCache", status_cache),
        cast("TaskiqTaskDispatcher", dispatcher),
        repository_session,
        repository_session.document_activity_repo,
        _processing_service(repository_session, status_cache, dispatcher),
    )

    with pytest.raises(RuntimeError):
        await handler(
            user_id=user_id,
            title="Fallback note",
            type=DocumentType.TEXT,
            raw_content="Hello world",
        )

    assert dispatcher.processed_document_ids == []


async def test_create_note_service_creates_markdown_document_and_queues_indexing() -> None:
    user_id = uuid.uuid4()
    document_repo = _FakeDocumentRepository()
    repository_session = _FakeRepositorySession(document_repo)
    status_cache = _FakeStatusCache()
    dispatcher = _SuccessfulTaskDispatcher()
    service = _note_service(repository_session, status_cache=status_cache, dispatcher=dispatcher)

    result = await service.create(
        user_id=user_id,
        body=CreateNoteRequest(
            title="Asyncio",
            content="Asyncio runs cooperative tasks on one event loop.",
            language="en",
        )
    )

    assert result.title == "Asyncio"
    assert result.status == DocumentStatus.QUEUED
    assert document_repo.created[0].type == DocumentType.MARKDOWN
    assert status_cache.calls[-1] == ("QUEUED", 0, "Queued note for memory indexing.")
    assert repository_session.document_processing_outbox_repo.created == [(result.id, "process_document")]
    assert dispatcher.processed_document_ids == []
    assert dispatcher.document_processing_outbox_dispatches == 0


async def test_list_notes_service_filters_and_counts_notes_in_repository() -> None:
    user_id = uuid.uuid4()
    note = _make_document(user_id=user_id)
    upload = _make_document(user_id=user_id)
    note = DocumentModel(
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
    service = _note_service(_FakeRepositorySession(document_repo))

    result = await service.list(user_id=user_id, limit=10, offset=0)

    assert result.total == 1
    assert [item.id for item in result.items] == [note.id]


async def test_get_note_service_returns_owned_note() -> None:
    user_id = uuid.uuid4()
    note = _make_note_document(user_id=user_id)
    service = _note_service(_FakeRepositorySession(_FakeDocumentRepository([note])))

    result = await service.get(user_id=user_id, note_id=note.id)

    assert result.id == note.id
    assert result.content == "Important text"


async def test_delete_note_service_deletes_owned_note() -> None:
    user_id = uuid.uuid4()
    note = _make_note_document(user_id=user_id)
    document_repo = _FakeDocumentRepository([note])
    repository_session = _FakeRepositorySession(document_repo)
    service = _note_service(repository_session)

    await service.delete(user_id=user_id, note_id=note.id)

    assert document_repo.deleted == [note.id]
    assert repository_session.committed is True


async def test_update_note_service_clears_chunks_for_empty_note() -> None:
    user_id = uuid.uuid4()
    base_note = _make_document(user_id=user_id)
    note = DocumentModel(
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
    repository_session = _FakeRepositorySession(document_repo)
    status_cache = _FakeStatusCache()
    dispatcher = _SuccessfulTaskDispatcher()
    service = _note_service(repository_session, status_cache=status_cache, dispatcher=dispatcher)

    result = await service.update(user_id=user_id, note_id=note.id, body=UpdateNoteRequest(title="Empty", content=""))

    assert result.status == DocumentStatus.READY
    assert repository_session.chunk_repo.deleted_document_ids == [note.id]
    assert dispatcher.document_processing_outbox_dispatches == 0


async def test_update_note_service_does_not_version_noop_update() -> None:
    user_id = uuid.uuid4()
    base_note = _make_document(user_id=user_id)
    note = DocumentModel(
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
    repository_session = _FakeRepositorySession(_FakeDocumentRepository([note]))
    service = _note_service(repository_session)

    await service.update(
        user_id=user_id,
        note_id=note.id,
        body=UpdateNoteRequest(title=note.title, content=note.raw_content or ""),
    )

    assert repository_session.note_version_repo.records == []


async def test_update_note_service_coalesces_autosave_versions() -> None:
    user_id = uuid.uuid4()
    base_note = _make_document(user_id=user_id)
    note = DocumentModel(
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
    repository_session = _FakeRepositorySession(_FakeDocumentRepository([note]))
    service = _note_service(repository_session)

    await service.update(user_id=user_id, note_id=note.id, body=UpdateNoteRequest(title=note.title, content="First autosave"))
    await service.update(user_id=user_id, note_id=note.id, body=UpdateNoteRequest(title=note.title, content="Second autosave"))

    assert len(repository_session.note_version_repo.records) == 1


async def test_list_note_versions_service_returns_owned_note_versions() -> None:
    user_id = uuid.uuid4()
    note = _make_note_document(user_id=user_id)
    repository_session = _FakeRepositorySession(_FakeDocumentRepository([note]))
    version_id = uuid.uuid4()
    repository_session.note_version_repo.records.append(
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
    service = _note_service(repository_session)

    result = await service.list_versions(user_id=user_id, note_id=note.id)

    assert [version.id for version in result] == [version_id]
    assert result[0].content == "Earlier content"


async def test_restore_note_version_service_restores_content_and_queues_processing() -> None:
    user_id = uuid.uuid4()
    note = _make_note_document(user_id=user_id, title="Current", content="Current content")
    repository_session = _FakeRepositorySession(_FakeDocumentRepository([note]))
    version_id = uuid.uuid4()
    repository_session.note_version_repo.records.append(
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
    service = _note_service(repository_session, status_cache=status_cache, dispatcher=dispatcher)

    result = await service.restore_version(user_id=user_id, note_id=note.id, version_id=version_id)

    assert result.title == "Restored"
    assert result.content == "Restored content"
    assert result.status == DocumentStatus.QUEUED
    assert len(repository_session.note_version_repo.records) == 2
    assert repository_session.document_processing_outbox_repo.created == [(note.id, "process_document")]
    assert dispatcher.processed_document_ids == []
    assert dispatcher.document_processing_outbox_dispatches == 0
