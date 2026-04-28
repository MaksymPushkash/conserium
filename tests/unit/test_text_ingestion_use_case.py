from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

import pytest

from src.application.dtos.ingestion_dtos import IngestTextDocumentDTO
from src.application.use_cases.documents.ingest_text_document_use_case import IngestTextDocumentUseCase
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType
from src.infrastructure.text_processing.simple_text_chunker import SimpleTextChunker

if TYPE_CHECKING:
    from src.application.interfaces.unit_of_work import IUnitOfWork
    from src.domain.entities.chunk_entity import ChunkEntity
    from src.domain.entities.document_entity import DocumentEntity


class _FakeDocumentRepository:
    def __init__(self) -> None:
        self.created: list[DocumentEntity] = []
        self.updated: list[DocumentEntity] = []

    async def create(self, document: DocumentEntity) -> None:
        self.created.append(document)

    async def update(self, document: DocumentEntity) -> None:
        self.updated.append(document)


class _FakeChunkRepository:
    def __init__(self) -> None:
        self.created_batches: list[list[ChunkEntity]] = []

    async def create_batch(self, chunks: list[ChunkEntity]) -> None:
        self.created_batches.append(chunks)


class _FakeUnitOfWork:
    def __init__(self) -> None:
        self.document_repo = _FakeDocumentRepository()
        self.chunk_repo = _FakeChunkRepository()
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> _FakeUnitOfWork:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is not None:
            self.rolled_back = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _as_uow(uow: _FakeUnitOfWork) -> IUnitOfWork:
    return cast("IUnitOfWork", uow)


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


async def test_ingest_text_document_use_case_persists_document_chunks_and_marks_ready() -> None:
    uow = _FakeUnitOfWork()
    use_case = IngestTextDocumentUseCase(_as_uow(uow), SimpleTextChunker(max_chunk_chars=80))
    user_id = uuid.uuid4()

    result = await use_case(
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
    assert len(uow.document_repo.created) == 1
    assert uow.document_repo.created[0].status == DocumentStatus.READY
    assert uow.document_repo.updated == [uow.document_repo.created[0]]
    assert len(uow.chunk_repo.created_batches) == 1
    assert len(uow.chunk_repo.created_batches[0]) == 1
    persisted_chunk = uow.chunk_repo.created_batches[0][0]
    assert persisted_chunk.document_id == result.id
    assert persisted_chunk.embedding == [0.0] * 1536
    assert persisted_chunk.chunk_index == 0
    assert persisted_chunk.content == "First paragraph.\n\nSecond paragraph."
    assert uow.committed is True


async def test_ingest_text_document_use_case_rejects_blank_text() -> None:
    use_case = IngestTextDocumentUseCase(_as_uow(_FakeUnitOfWork()), SimpleTextChunker())

    with pytest.raises(ValueError, match="raw_text cannot be empty"):
        await use_case(IngestTextDocumentDTO(user_id=uuid.uuid4(), title="Blank", raw_text="  \n"))
