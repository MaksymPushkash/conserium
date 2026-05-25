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
from src.application.use_cases.documents.process_image_document_use_case import ProcessImageDocumentUseCase
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
        collection_id: uuid.UUID | None = None,
        status: DocumentStatus | None = None,
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
    ) -> tuple[list[DocumentEntity], dict[DocumentStatus, int]]:
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

    async def dispatch_process_document(self, document_id: str) -> None:
        raise NotImplementedError

    async def dispatch_process_image_document(self, document_id: str) -> None:
        raise NotImplementedError

    async def dispatch_repo_sync_outbox(self) -> None:
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


class _FakeTextChunker(ITextChunker):
    def chunk_text(self, text: str) -> list[TextChunkDTO]:
        return [
            TextChunkDTO(
                content=text,
                chunk_index=0,
                start_char=0,
                end_char=len(text),
                token_count=6,
            )
        ]


class _FakeFileStorage(IFileStorage):
    async def save_document_file(self, *, user_id: uuid.UUID, filename: str, content: bytes) -> StoredFile:
        raise NotImplementedError

    async def read_document_file(self, path: str) -> bytes:
        return b"image-bytes"

    async def delete_document_file(self, path: str) -> None:
        return None


class _FakeImageExtractor(IContentExtractor):
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


def _make_image_document(*, language: str | None = None) -> DocumentEntity:
    document = DocumentEntity.create(
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
async def test_process_image_document_use_case_ocrs_and_dispatches_embeddings() -> None:
    document = _make_image_document()
    uow = _FakeUnitOfWork(_FakeDocumentRepository(document))
    status_cache = _FakeStatusCache()
    task_dispatcher = _FakeTaskDispatcher()

    use_case = ProcessImageDocumentUseCase(
        uow=uow,
        status_cache=status_cache,
        task_dispatcher=task_dispatcher,
        text_chunker=_FakeTextChunker(),
        file_storage=_FakeFileStorage(),
        image_extractor=_FakeImageExtractor(),
    )

    result = await use_case(str(document.id))

    assert result.status == "EMBEDDING_QUEUED"
    assert document.status == DocumentStatus.PROCESSING
    assert uow.commit_count == 1
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
async def test_process_image_document_use_case_passes_document_language_to_ocr() -> None:
    document = _make_image_document(language="ukr")
    uow = _FakeUnitOfWork(_FakeDocumentRepository(document))
    image_extractor = _FakeImageExtractor()

    use_case = ProcessImageDocumentUseCase(
        uow=uow,
        status_cache=_FakeStatusCache(),
        task_dispatcher=_FakeTaskDispatcher(),
        text_chunker=_FakeTextChunker(),
        file_storage=_FakeFileStorage(),
        image_extractor=image_extractor,
    )

    await use_case(str(document.id))

    assert image_extractor.called_language == "ukr"
