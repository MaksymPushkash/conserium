import uuid
from types import TracebackType
from typing import Any, cast

import pytest

from src.documents.document_repository import DocumentRepository
from src.documents.extraction import ContentExtractor, ExtractedContent
from src.documents.processing import ImageDocumentProcessor
from src.documents.repository import RelatedDocumentRecord
from src.documents.schemas import TextChunk
from src.documents.status import DocumentStatus
from src.documents.status_cache import RedisDocumentStatusCache
from src.documents.types import DocumentType
from src.kit.storage.file_storage import FileStorage, StoredFile
from src.models.document import DocumentModel
from src.worker.dispatcher import TaskiqTaskDispatcher


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


class _FakeTaskDispatcher(TaskiqTaskDispatcher):
    def __init__(self) -> None:
        self.embed_calls: list[dict[str, Any]] = []

    async def dispatch_process_document(self, document_id: str, *, task_id: str | None = None) -> None:
        raise NotImplementedError

    async def dispatch_process_image_document(self, document_id: str) -> None:
        raise NotImplementedError

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
                token_count=6,
            )
        ]


class _FakeFileStorage(FileStorage):
    async def save_document_file(self, *, user_id: uuid.UUID, filename: str, content: bytes) -> StoredFile:
        raise NotImplementedError

    async def read_document_file(self, path: str) -> bytes:
        return b"image-bytes"

    async def delete_document_file(self, path: str) -> None:
        return None


class _FakeImageExtractor(ContentExtractor):
    def __init__(self) -> None:
        self.called_language: str | None = None

    async def extract_from_bytes(
        self,
        data: bytes,
        *,
        filename: str = "",
        language: str | None = None,
    ) -> ExtractedContent:
        self.called_language = language
        return ExtractedContent(text="ocr text from image", title="scan", word_count=4)

    async def extract_from_url(self, url: str) -> ExtractedContent:
        raise NotImplementedError


def _make_image_document(*, language: str | None = None) -> DocumentModel:
    document = DocumentModel.create(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="Scan",
        type=DocumentType.IMAGE,
        file_path="/tmp/scan.png",
        language=language,
    )
    document.mark_queued()
    return document


@pytest.mark.asyncio
async def test_process_image_document_worker_ocrs_and_dispatches_embeddings() -> None:
    document = _make_image_document()
    repository_session = _FakeRepositorySession(_FakeDocumentRepository(document))
    status_cache = _FakeStatusCache()
    task_dispatcher = _FakeTaskDispatcher()

    handler = ImageDocumentProcessor(
        session=repository_session,  # type: ignore[arg-type]
        document_repo=cast("DocumentRepository", repository_session.document_repo),
        status_cache=status_cache,
        task_dispatcher=task_dispatcher,
        text_chunker=_FakeTextChunker(),
        file_storage=_FakeFileStorage(),
        image_extractor=_FakeImageExtractor(),
    )

    result = await handler(str(document.id))

    assert result.status == "EMBEDDING_QUEUED"
    assert document.status == DocumentStatus.PROCESSING
    assert repository_session.commit_count == 1
    assert status_cache.calls == [
        ("PROCESSING", 20, "Running OCR..."),
        ("PROCESSING", 40, "Splitting OCR text into chunks..."),
        ("PROCESSING", 60, "Queued for embedding..."),
    ]
    assert task_dispatcher.embed_calls == [
        {
            "document_id": str(document.id),
            "raw_text": "ocr text from image",
            "chunks_data": [
                {
                    "content": "ocr text from image",
                    "chunk_index": 0,
                    "start_char": 0,
                    "end_char": 19,
                    "page_number": None,
                    "token_count": 6,
                }
            ],
        }
    ]


@pytest.mark.asyncio
async def test_process_image_document_worker_passes_document_language_to_ocr() -> None:
    document = _make_image_document(language="ukr")
    repository_session = _FakeRepositorySession(_FakeDocumentRepository(document))
    image_extractor = _FakeImageExtractor()

    handler = ImageDocumentProcessor(
        session=repository_session,  # type: ignore[arg-type]
        document_repo=cast("DocumentRepository", repository_session.document_repo),
        status_cache=_FakeStatusCache(),
        task_dispatcher=_FakeTaskDispatcher(),
        text_chunker=_FakeTextChunker(),
        file_storage=_FakeFileStorage(),
        image_extractor=image_extractor,
    )

    await handler(str(document.id))

    assert image_extractor.called_language == "ukr"
