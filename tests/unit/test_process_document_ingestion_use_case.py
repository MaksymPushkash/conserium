import uuid
from types import TracebackType
from typing import Any

import pytest

from src.application.dtos.ingestion_dtos import TextChunkDTO
from src.application.ports.cache.document_status_cache import IDocumentStatusCache
from src.application.ports.ingestion.content_extractor import ExtractedContent, IContentExtractor
from src.application.ports.ingestion.file_storage import IFileStorage, StoredFile
from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
from src.application.ports.ingestion.text_chunker import ITextChunker
from src.application.ports.persistence.document_repository import IDocumentRepository
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.process_document_ingestion_use_case import (
    ProcessDocumentIngestionUseCase,
)
from src.domain.entities.document_entity import DocumentEntity
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType


class _FakeDocumentRepository(IDocumentRepository):
    def __init__(self, document: DocumentEntity | None) -> None:
        self.document = document
        self.updated_documents: list[DocumentEntity] = []

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentEntity | None:
        return self.document

    async def get_by_user_id(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        document_type: DocumentType | None = None,
    ) -> list[DocumentEntity]:
        raise NotImplementedError

    async def create(self, document: DocumentEntity) -> None:
        raise NotImplementedError

    async def update(self, document: DocumentEntity) -> None:
        self.updated_documents.append(document)

    async def delete(self, document_id: uuid.UUID) -> None:
        raise NotImplementedError

    async def exists(self, document_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def count_by_user_id(self, user_id: uuid.UUID, *, document_type: DocumentType | None = None) -> int:
        raise NotImplementedError


class _FakeUnitOfWork(IUnitOfWork):
    def __init__(self, document_repo: IDocumentRepository) -> None:
        self.document_repo = document_repo
        self.user_repo = None  # type: ignore[assignment]
        self.chunk_repo = None  # type: ignore[assignment]
        self.commit_count = 0

    async def __aenter__(self) -> "_FakeUnitOfWork":
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


class _FakeTaskDispatcher(ITaskDispatcher):
    def __init__(self) -> None:
        self.embed_calls: list[dict[str, Any]] = []
        self.audio_calls: list[str] = []
        self.image_calls: list[str] = []

    async def dispatch_process_document(self, document_id: str) -> None:
        raise NotImplementedError

    async def dispatch_process_audio_document(self, document_id: str) -> None:
        self.audio_calls.append(document_id)

    async def dispatch_process_image_document(self, document_id: str) -> None:
        self.image_calls.append(document_id)

    async def dispatch_embed_and_finalize_document(
        self,
        *,
        document_id: str,
        raw_text: str,
        chunks_data: list[dict[str, Any]],
        expected_content_hash: str | None = None,
    ) -> None:
        self.embed_calls.append(
            {
                "document_id": document_id,
                "raw_text": raw_text,
                "chunks_data": chunks_data,
                "expected_content_hash": expected_content_hash,
            }
        )


class _FakeTextChunker(ITextChunker):
    def chunk_text(self, text: str) -> list[TextChunkDTO]:
        return [
            TextChunkDTO(
                content=text,
                chunk_index=0,
                start_char=0,
                end_char=len(text),
                token_count=5,
            )
        ]


class _FakeFileStorage(IFileStorage):
    async def save_document_file(self, *, user_id: uuid.UUID, filename: str, content: bytes) -> StoredFile:
        raise NotImplementedError

    async def read_document_file(self, path: str) -> bytes:
        return b"%PDF-1.4 fake"

    async def delete_document_file(self, path: str) -> None:
        return None


class _UnusedExtractor(IContentExtractor):
    async def extract_from_bytes(
        self,
        data: bytes,
        *,
        filename: str = "",
        language: str | None = None,
    ) -> ExtractedContent:
        raise NotImplementedError

    async def extract_from_url(self, url: str) -> ExtractedContent:
        raise NotImplementedError


class _FakeUrlExtractor(IContentExtractor):
    def __init__(self, extracted_content: ExtractedContent) -> None:
        self.extracted_content = extracted_content
        self.called_url: str | None = None

    async def extract_from_bytes(
        self,
        data: bytes,
        *,
        filename: str = "",
        language: str | None = None,
    ) -> ExtractedContent:
        raise NotImplementedError

    async def extract_from_url(self, url: str) -> ExtractedContent:
        self.called_url = url
        return self.extracted_content


def _make_document(
    *,
    document_type: DocumentType,
    raw_content: str | None = None,
    source_url: str | None = None,
    file_path: str | None = None,
) -> DocumentEntity:
    document = DocumentEntity.create(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="Doc",
        type=document_type,
        raw_content=raw_content,
        source_url=source_url,
        file_path=file_path,
    )
    document.mark_queued()
    return document


@pytest.mark.asyncio
async def test_process_document_ingestion_use_case_dispatches_embedding_work() -> None:
    document = _make_document(document_type=DocumentType.TEXT, raw_content="hello world")
    document_repo = _FakeDocumentRepository(document)
    uow = _FakeUnitOfWork(document_repo)
    status_cache = _FakeStatusCache()
    task_dispatcher = _FakeTaskDispatcher()

    use_case = ProcessDocumentIngestionUseCase(
        uow=uow,
        status_cache=status_cache,
        task_dispatcher=task_dispatcher,
        text_chunker=_FakeTextChunker(),
        file_storage=_FakeFileStorage(),
        url_extractor=_UnusedExtractor(),
        youtube_extractor=_UnusedExtractor(),
        pdf_extractor=_UnusedExtractor(),
    )

    result = await use_case(str(document.id))

    assert result.status == "EMBEDDING_QUEUED"
    assert document.status == DocumentStatus.PROCESSING
    assert uow.commit_count == 1
    assert status_cache.calls == [
        ("PROCESSING", 10, "Extracting content..."),
        ("PROCESSING", 40, "Splitting into chunks..."),
        ("PROCESSING", 60, "Queued for embedding..."),
    ]
    assert len(task_dispatcher.embed_calls) == 1
    assert task_dispatcher.embed_calls[0]["raw_text"] == "hello world"
    assert task_dispatcher.embed_calls[0]["expected_content_hash"] is not None
    assert task_dispatcher.embed_calls[0]["chunks_data"][0]["page_number"] is None


@pytest.mark.asyncio
async def test_process_document_ingestion_use_case_returns_not_found() -> None:
    use_case = ProcessDocumentIngestionUseCase(
        uow=_FakeUnitOfWork(_FakeDocumentRepository(None)),
        status_cache=_FakeStatusCache(),
        task_dispatcher=_FakeTaskDispatcher(),
        text_chunker=_FakeTextChunker(),
        file_storage=_FakeFileStorage(),
        url_extractor=_UnusedExtractor(),
        youtube_extractor=_UnusedExtractor(),
        pdf_extractor=_UnusedExtractor(),
    )

    result = await use_case(str(uuid.uuid4()))

    assert result.status == "NOT_FOUND"


@pytest.mark.asyncio
async def test_process_document_ingestion_use_case_extracts_youtube_content() -> None:
    document = _make_document(document_type=DocumentType.YOUTUBE, source_url="https://youtu.be/abc123")
    youtube_extractor = _FakeUrlExtractor(
        ExtractedContent(
            text="first transcript line\nsecond transcript line",
            title="YouTube abc123",
            word_count=6,
        )
    )
    task_dispatcher = _FakeTaskDispatcher()

    use_case = ProcessDocumentIngestionUseCase(
        uow=_FakeUnitOfWork(_FakeDocumentRepository(document)),
        status_cache=_FakeStatusCache(),
        task_dispatcher=task_dispatcher,
        text_chunker=_FakeTextChunker(),
        file_storage=_FakeFileStorage(),
        url_extractor=_UnusedExtractor(),
        youtube_extractor=youtube_extractor,
        pdf_extractor=_UnusedExtractor(),
    )

    result = await use_case(str(document.id))

    assert result.status == "EMBEDDING_QUEUED"
    assert youtube_extractor.called_url == "https://youtu.be/abc123"
    assert task_dispatcher.embed_calls[0]["raw_text"] == "first transcript line\nsecond transcript line"


@pytest.mark.asyncio
async def test_process_document_ingestion_use_case_dispatches_audio_to_media_worker() -> None:
    document = _make_document(document_type=DocumentType.AUDIO, file_path="/tmp/audio.m4a")
    status_cache = _FakeStatusCache()
    task_dispatcher = _FakeTaskDispatcher()

    use_case = ProcessDocumentIngestionUseCase(
        uow=_FakeUnitOfWork(_FakeDocumentRepository(document)),
        status_cache=status_cache,
        task_dispatcher=task_dispatcher,
        text_chunker=_FakeTextChunker(),
        file_storage=_FakeFileStorage(),
        url_extractor=_UnusedExtractor(),
        youtube_extractor=_UnusedExtractor(),
        pdf_extractor=_UnusedExtractor(),
    )

    result = await use_case(str(document.id))

    assert result.status == "MEDIA_QUEUED"
    assert document.status == DocumentStatus.PROCESSING
    assert status_cache.calls == [
        ("PROCESSING", 10, "Queued for audio transcription..."),
    ]
    assert task_dispatcher.audio_calls == [str(document.id)]
    assert task_dispatcher.embed_calls == []


@pytest.mark.asyncio
async def test_process_document_ingestion_use_case_dispatches_image_to_media_worker() -> None:
    document = _make_document(document_type=DocumentType.IMAGE, file_path="/tmp/image.png")
    status_cache = _FakeStatusCache()
    task_dispatcher = _FakeTaskDispatcher()

    use_case = ProcessDocumentIngestionUseCase(
        uow=_FakeUnitOfWork(_FakeDocumentRepository(document)),
        status_cache=status_cache,
        task_dispatcher=task_dispatcher,
        text_chunker=_FakeTextChunker(),
        file_storage=_FakeFileStorage(),
        url_extractor=_UnusedExtractor(),
        youtube_extractor=_UnusedExtractor(),
        pdf_extractor=_UnusedExtractor(),
    )

    result = await use_case(str(document.id))

    assert result.status == "MEDIA_QUEUED"
    assert document.status == DocumentStatus.PROCESSING
    assert status_cache.calls == [
        ("PROCESSING", 10, "Queued for OCR..."),
    ]
    assert task_dispatcher.image_calls == [str(document.id)]
    assert task_dispatcher.embed_calls == []
