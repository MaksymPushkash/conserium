import uuid
from types import TracebackType
from typing import Any, cast

import pytest

from src.documents.document_repository import DocumentRepository
from src.documents.extraction import ContentExtractor, ExtractedContent
from src.documents.processing import DocumentIngestionProcessor
from src.documents.repository import RelatedDocumentRecord
from src.documents.schemas import TextChunk
from src.documents.status import DocumentStatus
from src.documents.status_cache import RedisDocumentStatusCache
from src.documents.types import DocumentType
from src.kit.storage.file_storage import FileStorage, StoredFile
from src.models.document import DocumentModel
from src.worker.dispatcher import CeleryTaskDispatcher


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


class _FakeRepositorySession:
    def __init__(self, document_repo: DocumentRepository) -> None:
        self.document_repo = document_repo
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


class _FakeStatusCache(RedisDocumentStatusCache):
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str]] = []

    async def set_status(self, document_id: uuid.UUID, status: str, progress: int, message: str) -> None:
        self.calls.append((status, progress, message))

    async def get_status(self, document_id: uuid.UUID) -> None:
        raise NotImplementedError

    async def delete_status(self, document_id: uuid.UUID) -> None:
        raise NotImplementedError


class _FakeTaskDispatcher(CeleryTaskDispatcher):
    def __init__(self) -> None:
        self.embed_calls: list[dict[str, Any]] = []
        self.image_calls: list[str] = []

    async def dispatch_process_document(self, document_id: str, *, task_id: str | None = None) -> None:
        raise NotImplementedError

    async def dispatch_process_image_document(self, document_id: str) -> None:
        self.image_calls.append(document_id)

    async def dispatch_repo_sync_outbox(self) -> None:
        raise NotImplementedError

    async def dispatch_document_processing_outbox(self) -> None:
        raise NotImplementedError

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


class _FakeTextChunker:
    def chunk_text(self, text: str) -> list[TextChunk]:
        return [
            TextChunk(
                content=text,
                chunk_index=0,
                start_char=0,
                end_char=len(text),
                token_count=5,
            )
        ]


class _FakeFileStorage(FileStorage):
    async def save_document_file(self, *, user_id: uuid.UUID, filename: str, content: bytes) -> StoredFile:
        raise NotImplementedError

    async def read_document_file(self, path: str) -> bytes:
        return b"%PDF-1.4 fake"

    async def delete_document_file(self, path: str) -> None:
        return None


class _UnusedExtractor(ContentExtractor):
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


class _FakeUrlExtractor(ContentExtractor):
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
) -> DocumentModel:
    document = DocumentModel.create(
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
async def test_process_document_ingestion_service_dispatches_embedding_work() -> None:
    document = _make_document(document_type=DocumentType.TEXT, raw_content="hello world")
    document_repo = _FakeDocumentRepository(document)
    repository_session = _FakeRepositorySession(document_repo)
    status_cache = _FakeStatusCache()
    task_dispatcher = _FakeTaskDispatcher()

    handler = DocumentIngestionProcessor(
        session=repository_session,  # type: ignore[arg-type]
        document_repo=cast("DocumentRepository", repository_session.document_repo),
        status_cache=status_cache,
        task_dispatcher=task_dispatcher,
        text_chunker=_FakeTextChunker(),
        file_storage=_FakeFileStorage(),
        url_extractor=_UnusedExtractor(),
        youtube_extractor=_UnusedExtractor(),
        pdf_extractor=_UnusedExtractor(),
    )

    result = await handler(str(document.id))

    assert result.status == "EMBEDDING_QUEUED"
    assert document.status == DocumentStatus.PROCESSING
    assert repository_session.commit_count == 1
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
async def test_process_document_ingestion_service_returns_not_found() -> None:
    repository_session = _FakeRepositorySession(_FakeDocumentRepository(None))
    handler = DocumentIngestionProcessor(
        session=repository_session,  # type: ignore[arg-type]
        document_repo=cast("DocumentRepository", repository_session.document_repo),
        status_cache=_FakeStatusCache(),
        task_dispatcher=_FakeTaskDispatcher(),
        text_chunker=_FakeTextChunker(),
        file_storage=_FakeFileStorage(),
        url_extractor=_UnusedExtractor(),
        youtube_extractor=_UnusedExtractor(),
        pdf_extractor=_UnusedExtractor(),
    )

    result = await handler(str(uuid.uuid4()))

    assert result.status == "NOT_FOUND"


@pytest.mark.asyncio
async def test_process_document_ingestion_service_extracts_youtube_content() -> None:
    document = _make_document(document_type=DocumentType.YOUTUBE, source_url="https://youtu.be/abc123")
    youtube_extractor = _FakeUrlExtractor(
        ExtractedContent(
            text="first transcript line\nsecond transcript line",
            title="YouTube abc123",
            word_count=6,
        )
    )
    task_dispatcher = _FakeTaskDispatcher()
    repository_session = _FakeRepositorySession(_FakeDocumentRepository(document))

    handler = DocumentIngestionProcessor(
        session=repository_session,  # type: ignore[arg-type]
        document_repo=cast("DocumentRepository", repository_session.document_repo),
        status_cache=_FakeStatusCache(),
        task_dispatcher=task_dispatcher,
        text_chunker=_FakeTextChunker(),
        file_storage=_FakeFileStorage(),
        url_extractor=_UnusedExtractor(),
        youtube_extractor=youtube_extractor,
        pdf_extractor=_UnusedExtractor(),
    )

    result = await handler(str(document.id))

    assert result.status == "EMBEDDING_QUEUED"
    assert youtube_extractor.called_url == "https://youtu.be/abc123"
    assert task_dispatcher.embed_calls[0]["raw_text"] == "first transcript line\nsecond transcript line"


@pytest.mark.asyncio
async def test_process_document_ingestion_service_dispatches_image_to_media_worker() -> None:
    document = _make_document(document_type=DocumentType.IMAGE, file_path="/tmp/image.png")
    status_cache = _FakeStatusCache()
    task_dispatcher = _FakeTaskDispatcher()
    repository_session = _FakeRepositorySession(_FakeDocumentRepository(document))

    handler = DocumentIngestionProcessor(
        session=repository_session,  # type: ignore[arg-type]
        document_repo=cast("DocumentRepository", repository_session.document_repo),
        status_cache=status_cache,
        task_dispatcher=task_dispatcher,
        text_chunker=_FakeTextChunker(),
        file_storage=_FakeFileStorage(),
        url_extractor=_UnusedExtractor(),
        youtube_extractor=_UnusedExtractor(),
        pdf_extractor=_UnusedExtractor(),
    )

    result = await handler(str(document.id))

    assert result.status == "MEDIA_QUEUED"
    assert document.status == DocumentStatus.PROCESSING
    assert status_cache.calls == [
        ("PROCESSING", 10, "Queued for OCR..."),
    ]
    assert task_dispatcher.image_calls == [str(document.id)]
    assert task_dispatcher.embed_calls == []
