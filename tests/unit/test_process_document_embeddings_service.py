import hashlib
import uuid
from types import TracebackType
from typing import cast

import pytest

from src.documents.chunk_repository import ChunkRepository
from src.documents.document_repository import DocumentRepository
from src.documents.processing import DocumentEmbeddingProcessor
from src.documents.repository import (
    ChunkSearchResult,
    RelatedDocumentRecord,
)
from src.documents.status import DocumentStatus
from src.documents.status_cache import IDocumentStatusCache
from src.documents.types import DocumentType
from src.kit.ports.ai.embedding_provider import IEmbeddingProvider
from src.models.chunk import ChunkModel
from src.models.document import DocumentModel


class _FakeDocumentRepository(DocumentRepository):
    def __init__(self, document: DocumentModel | None) -> None:
        self.document = document
        self.updated_documents: list[DocumentModel] = []

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentModel | None:
        return self.document

    async def get_by_user_id(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        document_type: DocumentType | None = None,
        collection_id: uuid.UUID | None = None,
        status: DocumentStatus | None = None,
    ) -> list[DocumentModel]:
        raise NotImplementedError

    async def create(self, document: DocumentModel) -> None:
        raise NotImplementedError

    async def update(self, document: DocumentModel) -> None:
        self.updated_documents.append(document)

    async def delete(self, document_id: uuid.UUID) -> None:
        raise NotImplementedError

    async def add_manual_tags(self, *, document_id: uuid.UUID, user_id: uuid.UUID, tag_names: list[str]) -> None:
        raise NotImplementedError

    async def exists(self, document_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def count_by_user_id(
        self,
        user_id: uuid.UUID,
        *,
        document_type: DocumentType | None = None,
        collection_id: uuid.UUID | None = None,
        status: DocumentStatus | None = None,
    ) -> int:
        raise NotImplementedError

    async def count_by_status(
        self,
        user_id: uuid.UUID,
        *,
        collection_id: uuid.UUID | None = None,
    ) -> dict[DocumentStatus, int]:
        raise NotImplementedError

    async def get_collection_documents_with_status_counts(
        self,
        user_id: uuid.UUID,
        *,
        collection_id: uuid.UUID,
        limit: int = 200,
    ) -> tuple[list[DocumentModel], dict[DocumentStatus, int]]:
        raise NotImplementedError

    async def get_related_documents(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        limit: int = 5,
    ) -> list[RelatedDocumentRecord]:
        raise NotImplementedError


class _FakeChunkRepository(ChunkRepository):
    def __init__(self) -> None:
        self.deleted_document_ids: list[uuid.UUID] = []
        self.created_batches: list[list[ChunkModel]] = []

    async def get_by_id(self, chunk_id: uuid.UUID) -> ChunkModel | None:
        raise NotImplementedError

    async def get_by_document_id(self, document_id: uuid.UUID) -> list[ChunkModel]:
        raise NotImplementedError

    async def create_batch(self, chunks: list[ChunkModel]) -> None:
        self.created_batches.append(chunks)

    async def delete_by_document_id(self, document_id: uuid.UUID) -> None:
        self.deleted_document_ids.append(document_id)

    async def semantic_search(
        self,
        embedding: list[float],
        user_id: uuid.UUID,
        *,
        limit: int = 10,
        collection_id: uuid.UUID | None = None,
    ) -> list[ChunkModel]:
        raise NotImplementedError

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
        raise NotImplementedError


class _FakeRepositorySession:
    def __init__(self, document_repo: DocumentRepository, chunk_repo: ChunkRepository) -> None:
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo
        self.commit_count = 0

    async def __aenter__(self) -> "_FakeRepositorySession":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        return None


class _FakeStatusCache(IDocumentStatusCache):
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str]] = []

    async def set_status(self, document_id: uuid.UUID, status: str, progress: int, message: str) -> None:
        self.calls.append((status, progress, message))

    async def get_status(self, document_id: uuid.UUID) -> None:
        raise NotImplementedError

    async def delete_status(self, document_id: uuid.UUID) -> None:
        raise NotImplementedError


class _FakeEmbeddingProvider(IEmbeddingProvider):
    async def embed_text(self, text: str) -> list[float]:
        return [0.1] * ChunkModel.EMBEDDING_DIMENSIONS

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * ChunkModel.EMBEDDING_DIMENSIONS for _ in texts]


def _make_document(*, raw_content: str | None = None) -> DocumentModel:
    document = DocumentModel.create(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="Doc",
        type=DocumentType.TEXT,
        raw_content=raw_content,
    )
    document.mark_queued()
    return document


@pytest.mark.asyncio
async def test_process_document_embeddings_service_persists_chunks_and_marks_ready() -> None:
    document = _make_document()
    document_repo = _FakeDocumentRepository(document)
    chunk_repo = _FakeChunkRepository()
    repository_session = _FakeRepositorySession(document_repo, chunk_repo)
    status_cache = _FakeStatusCache()

    handler = DocumentEmbeddingProcessor(
        session=repository_session,  # type: ignore[arg-type]
        document_repo=cast("DocumentRepository", repository_session.document_repo),
        status_cache=status_cache,
        embedding_provider=_FakeEmbeddingProvider(),
        chunk_repo=chunk_repo,
    )

    result = await handler(
        document_id=str(document.id),
        raw_text="hello world",
        chunks_data=[
            {
                "content": "hello world",
                "chunk_index": 0,
                "start_char": 0,
                "end_char": 11,
                "page_number": 2,
                "token_count": 5,
            }
        ],
    )

    assert result.status == "READY"
    assert document.status == DocumentStatus.READY
    assert document.raw_content == "hello world"
    assert chunk_repo.deleted_document_ids == [document.id]
    assert len(chunk_repo.created_batches) == 1
    assert chunk_repo.created_batches[0][0].page_number == 2
    assert repository_session.commit_count == 1
    assert status_cache.calls == [
        ("PROCESSING", 70, "Generating embeddings..."),
        ("PROCESSING", 90, "Saving to database..."),
        ("READY", 100, "Processing complete."),
    ]


@pytest.mark.asyncio
async def test_process_document_embeddings_service_returns_not_found() -> None:
    chunk_repo = _FakeChunkRepository()
    repository_session = _FakeRepositorySession(_FakeDocumentRepository(None), chunk_repo)
    handler = DocumentEmbeddingProcessor(
        session=repository_session,  # type: ignore[arg-type]
        document_repo=cast("DocumentRepository", repository_session.document_repo),
        status_cache=_FakeStatusCache(),
        embedding_provider=_FakeEmbeddingProvider(),
        chunk_repo=chunk_repo,
    )

    result = await handler(
        document_id=str(uuid.uuid4()),
        raw_text="hello",
        chunks_data=[],
    )

    assert result.status == "NOT_FOUND"


@pytest.mark.asyncio
async def test_process_document_embeddings_service_skips_stale_text_job() -> None:
    document = _make_document(raw_content="new content")
    document_repo = _FakeDocumentRepository(document)
    chunk_repo = _FakeChunkRepository()
    repository_session = _FakeRepositorySession(document_repo, chunk_repo)
    status_cache = _FakeStatusCache()
    old_hash = hashlib.sha256(b"old content").hexdigest()

    handler = DocumentEmbeddingProcessor(
        session=repository_session,  # type: ignore[arg-type]
        document_repo=cast("DocumentRepository", repository_session.document_repo),
        status_cache=status_cache,
        embedding_provider=_FakeEmbeddingProvider(),
        chunk_repo=chunk_repo,
    )

    result = await handler(
        document_id=str(document.id),
        raw_text="old content",
        chunks_data=[{"content": "old content", "chunk_index": 0}],
        expected_content_hash=old_hash,
    )

    assert result.status == "STALE"
    assert chunk_repo.created_batches == []
    assert repository_session.commit_count == 0
    assert status_cache.calls == []
