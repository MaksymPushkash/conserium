from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

import pytest

from src.documents.ingestion import TextDocumentIngester
from src.documents.schemas import IngestTextDocumentDTO
from src.documents.status import DocumentStatus
from src.documents.text_chunker import SimpleTextChunker
from src.documents.types import DocumentType
from src.kit.exceptions import DocumentValidationException

if TYPE_CHECKING:
    from src.documents.document_repository import DocumentRepository
    from src.models.chunk import ChunkModel
    from src.models.document import DocumentModel


class _FakeDocumentRepository:
    def __init__(self) -> None:
        self.created: list[DocumentModel] = []
        self.updated: list[DocumentModel] = []

    async def create(self, document: DocumentModel) -> None:
        self.created.append(document)

    async def update(self, document: DocumentModel) -> None:
        self.updated.append(document)


class _FakeChunkRepository:
    def __init__(self) -> None:
        self.created_batches: list[list[ChunkModel]] = []

    async def create_batch(self, chunks: list[ChunkModel]) -> None:
        self.created_batches.append(chunks)


class _FakeRepositorySession:
    def __init__(self) -> None:
        self.document_repo = _FakeDocumentRepository()
        self.collection_repo = _FakeCollectionRepository()
        self.shared_workspace_repo = _FakeSharedWorkspaceRepository()
        self.chunk_repo = _FakeChunkRepository()
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> _FakeRepositorySession:
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


def _as_document_repository(repository_session: _FakeRepositorySession) -> DocumentRepository:
    return cast("DocumentRepository", repository_session.document_repo)


def test_simple_text_chunker_preserves_offsets_and_ignores_blank_text() -> None:
    text = "  First paragraph.\n\nSecond paragraph has more words.  "
    chunker = SimpleTextChunker(max_chunk_chars=80)

    assert chunker.chunk_text(" \n\t ") == []

    chunks = chunker.chunk_text(text)

    assert len(chunks) == 1
    assert chunks[0].content == "First paragraph.\n\nSecond paragraph has more words."
    assert text[chunks[0].start_char : chunks[0].end_char] == chunks[0].content
    assert chunks[0].chunk_index == 0
    assert chunks[0].token_count == 7


def test_simple_text_chunker_splits_long_paragraphs() -> None:
    text = "alpha beta gamma delta epsilon zeta eta theta"
    chunker = SimpleTextChunker(max_chunk_chars=20)

    chunks = chunker.chunk_text(text)

    assert len(chunks) > 1
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.content == text[chunk.start_char : chunk.end_char] for chunk in chunks)
    assert all(len(chunk.content) <= 20 for chunk in chunks)


async def test_ingest_text_document_service_persists_document_chunks_and_marks_ready() -> None:
    repository_session = _FakeRepositorySession()
    handler = TextDocumentIngester(
        repository_session,  # type: ignore[arg-type]
        _as_document_repository(repository_session),
        SimpleTextChunker(max_chunk_chars=80),
        repository_session,
        repository_session.chunk_repo,
    )
    user_id = uuid.uuid4()

    result = await handler(
        IngestTextDocumentDTO(
            user_id=user_id,
            title="Research note",
            raw_text="First paragraph.\n\nSecond paragraph.",
            type=DocumentType.TEXT,
            language="en",
        )
    )

    assert result.user_id == user_id
    assert result.title == "Research note"
    assert result.status == DocumentStatus.READY
    assert len(repository_session.document_repo.created) == 1
    assert repository_session.document_repo.created[0].status == DocumentStatus.READY
    assert repository_session.document_repo.updated == [repository_session.document_repo.created[0]]
    assert len(repository_session.chunk_repo.created_batches) == 1
    assert len(repository_session.chunk_repo.created_batches[0]) == 1
    persisted_chunk = repository_session.chunk_repo.created_batches[0][0]
    assert persisted_chunk.document_id == result.id
    assert persisted_chunk.embedding == [0.0] * 1536
    assert persisted_chunk.chunk_index == 0
    assert persisted_chunk.content == "First paragraph.\n\nSecond paragraph."
    assert repository_session.committed is True


async def test_ingest_text_document_service_rejects_blank_text() -> None:
    repository_session = _FakeRepositorySession()
    handler = TextDocumentIngester(
        repository_session,  # type: ignore[arg-type]
        _as_document_repository(repository_session),
        SimpleTextChunker(),
        repository_session,
        repository_session.chunk_repo,
    )

    with pytest.raises(DocumentValidationException, match="raw_text cannot be empty"):
        await handler(IngestTextDocumentDTO(user_id=uuid.uuid4(), title="Blank", raw_text="  \n"))
