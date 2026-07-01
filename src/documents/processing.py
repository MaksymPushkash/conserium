from __future__ import annotations

import hashlib
import logging
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.billing.service import billing
from src.documents.extraction import ExtractedContent
from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.kit.exceptions import DocumentValidationException
from src.models.chunk import ChunkModel

if TYPE_CHECKING:
    from fastapi import BackgroundTasks

    from src.documents.chunk_repository import ChunkRepository
    from src.documents.document_repository import DocumentRepository
    from src.documents.extraction import ContentExtractor
    from src.documents.processing_outbox_repository import DocumentProcessingOutboxRepository
    from src.documents.schemas import DocumentProcessingOutboxRecord
    from src.documents.services.enrichment.enrichment_service import EnrichmentService
    from src.documents.status_cache import RedisDocumentStatusCache
    from src.documents.text_chunker import SimpleTextChunker
    from src.kit.ai.embedding_provider import EmbeddingProvider
    from src.kit.storage.file_storage import FileStorage
    from src.models.document import DocumentModel
    from src.postgres import AsyncSession
    from src.worker.dispatcher import TaskiqTaskDispatcher

DOCUMENT_PROCESSING_TASK_NAME = "process_document"
_MAX_OUTBOX_ATTEMPTS = 5
_OUTBOX_LOCK_TIMEOUT = timedelta(minutes=15)
_OUTBOX_BATCH_LIMIT = 100

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DocumentProcessingOutboxDrainResult:
    claimed: int
    dispatched: int
    failed: int
    permanently_failed: int


class DocumentProcessingService:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        outbox_repo: DocumentProcessingOutboxRepository,
        status_cache: RedisDocumentStatusCache,
        task_dispatcher: TaskiqTaskDispatcher,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._outbox_repo = outbox_repo
        self._status_cache = status_cache
        self._task_dispatcher = task_dispatcher
        self._background_tasks = background_tasks

    async def drain(self, *, limit: int = _OUTBOX_BATCH_LIMIT) -> DocumentProcessingOutboxDrainResult:
        outbox_items = await self._claim_outbox(limit)
        dispatched = 0
        failed = 0
        permanently_failed = 0

        for outbox in outbox_items:
            try:
                await self._dispatch_outbox_item(outbox)
                dispatched += 1
            except Exception as exc:
                retryable = outbox.attempts < _MAX_OUTBOX_ATTEMPTS
                await self._mark_outbox_failed(outbox, exc, retryable=retryable)
                failed += 1
                if not retryable:
                    permanently_failed += 1
                    await self._mark_document_failed(outbox.document_id, "Document processing dispatch failed after retries.")

        return DocumentProcessingOutboxDrainResult(
            claimed=len(outbox_items),
            dispatched=dispatched,
            failed=failed,
            permanently_failed=permanently_failed,
        )

    async def queue(self, document: DocumentModel, *, message: str) -> None:
        await self.enqueue(document, message=message)
        if self._background_tasks is not None:
            self._background_tasks.add_task(self._task_dispatcher.dispatch_document_processing_outbox)

    async def enqueue(self, document: DocumentModel, *, message: str) -> DocumentProcessingOutboxRecord:
        document.mark_queued()
        await self._document_repo.update(document)
        outbox = await self._outbox_repo.create_outbox(
            document_id=document.id,
            task_name=DOCUMENT_PROCESSING_TASK_NAME,
        )
        await self._session.flush()

        with suppress(Exception):
            await self._status_cache.set_status(
                document.id,
                status="QUEUED",
                progress=0,
                message=message,
            )
        return outbox

    async def acknowledge(self, *, task_id: str | None, document_id: UUID) -> bool:
        outbox_id = document_processing_outbox_id_from_task_id(task_id)
        if outbox_id is None:
            return True
        outbox = await self._outbox_repo.get_by_id(outbox_id)
        if outbox is None or outbox.document_id != document_id:
            return False
        if outbox.status == "dispatched":
            return False
        await self._outbox_repo.mark_dispatched(outbox_id, datetime.now(UTC))
        await self._session.commit()
        return True

    async def _claim_outbox(self, limit: int) -> list[DocumentProcessingOutboxRecord]:
        now = datetime.now(UTC)
        outbox_items = await self._outbox_repo.claim_batch(
            limit=limit,
            locked_at=now,
            stale_before=now - _OUTBOX_LOCK_TIMEOUT,
            max_attempts=_MAX_OUTBOX_ATTEMPTS,
        )
        await self._session.commit()
        return outbox_items

    async def _dispatch_outbox_item(self, outbox: DocumentProcessingOutboxRecord) -> None:
        document = await self._load_document(outbox.document_id)
        if document is None:
            await self._mark_outbox_dispatched(outbox)
            return

        if document.status in (DocumentStatus.PROCESSING, DocumentStatus.READY):
            await self._mark_outbox_dispatched(outbox)
            return

        document_user_id = document.user_id
        await self._status_cache.set_status(
            outbox.document_id,
            status=DocumentStatus.QUEUED.value,
            progress=0,
            message="Queued for processing.",
        )

        document = await self._document_repo.get_by_id(outbox.document_id)
        if document is not None:
            document.mark_queued()
            await self._document_repo.update(document)
        await self._session.commit()

        priority = await self._processing_priority(document_user_id)
        if priority is None:
            await self._task_dispatcher.dispatch_process_document(
                str(outbox.document_id),
                task_id=document_processing_outbox_task_id(outbox.id),
            )
        else:
            await self._task_dispatcher.dispatch_process_document(
                str(outbox.document_id),
                task_id=document_processing_outbox_task_id(outbox.id),
                priority=priority,
            )

    async def _load_document(self, document_id: UUID) -> DocumentModel | None:
        return await self._document_repo.get_by_id(document_id)

    async def _processing_priority(self, user_id: UUID) -> int | None:
        try:
            if await billing.has_priority_processing(self._session, user_id=user_id):
                return 9
        except Exception:
            logger.warning("document_processing_priority_lookup_failed", exc_info=True)
        return None

    async def _mark_outbox_dispatched(self, outbox: DocumentProcessingOutboxRecord) -> None:
        await self._outbox_repo.mark_dispatched(outbox.id, datetime.now(UTC))
        await self._session.commit()

    async def _mark_outbox_failed(
        self,
        outbox: DocumentProcessingOutboxRecord,
        exc: Exception,
        *,
        retryable: bool,
    ) -> None:
        await self._outbox_repo.mark_failed(
            outbox.id,
            last_error=_sanitize_outbox_error(exc),
            retryable=retryable,
        )
        await self._session.commit()

    async def _mark_document_failed(self, document_id: UUID, message: str) -> None:
        try:
            document = await self._document_repo.get_by_id(document_id)
            if document is not None:
                document.mark_failed()
                await self._document_repo.update(document)
            await self._session.commit()
            await self._status_cache.set_status(document_id, status="FAILED", progress=0, message=message)
        except Exception as exc:
            logger.exception(
                "document_processing_failed_state_persistence_failed",
                extra={
                    "document_id": str(document_id),
                    "error_type": type(exc).__name__,
                    "sanitized_error": message,
                },
            )


def document_processing_outbox_task_id(outbox_id: UUID) -> str:
    return f"document-processing-outbox-{outbox_id}"


def document_processing_outbox_id_from_task_id(task_id: str | None) -> UUID | None:
    prefix = "document-processing-outbox-"
    if not task_id or not task_id.startswith(prefix):
        return None
    try:
        return UUID(task_id[len(prefix):])
    except ValueError:
        return None


def _sanitize_outbox_error(exc: Exception) -> str:
    message = str(exc).strip() or type(exc).__name__
    return message[:500]


@dataclass(frozen=True, slots=True)
class ProcessDocumentIngestionResult:
    document_id: str
    status: str


class DocumentIngestionProcessor:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        status_cache: RedisDocumentStatusCache,
        task_dispatcher: TaskiqTaskDispatcher,
        text_chunker: SimpleTextChunker,
        file_storage: FileStorage,
        url_extractor: ContentExtractor,
        youtube_extractor: ContentExtractor,
        pdf_extractor: ContentExtractor,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._status_cache = status_cache
        self._task_dispatcher = task_dispatcher
        self._text_chunker = text_chunker
        self._file_storage = file_storage
        self._url_extractor = url_extractor
        self._youtube_extractor = youtube_extractor
        self._pdf_extractor = pdf_extractor

    async def __call__(self, document_id: str) -> ProcessDocumentIngestionResult:
        document = await self._load_document(document_id)
        if document is None:
            return ProcessDocumentIngestionResult(document_id=document_id, status="NOT_FOUND")

        if document.type == DocumentType.IMAGE:
            await self._status_cache.set_status(
                document.id,
                status="PROCESSING",
                progress=10,
                message="Queued for OCR...",
            )
            await self._mark_processing(document)
            await self._task_dispatcher.dispatch_process_image_document(document_id)
            return ProcessDocumentIngestionResult(document_id=document_id, status="MEDIA_QUEUED")

        await self._status_cache.set_status(
            document.id,
            status="PROCESSING",
            progress=10,
            message="Extracting content...",
        )
        await self._mark_processing(document)

        extracted = await self._extract_document(document)

        await self._status_cache.set_status(
            document.id,
            status="PROCESSING",
            progress=40,
            message="Splitting into chunks...",
        )
        chunks_data = self._build_chunks_data(extracted)

        await self._status_cache.set_status(
            document.id,
            status="PROCESSING",
            progress=60,
            message="Queued for embedding...",
        )
        await self._task_dispatcher.dispatch_embed_and_finalize_document(
            document_id=document_id,
            raw_text=extracted.text,
            chunks_data=chunks_data,
            expected_content_hash=(
                _content_hash(extracted.text) if document.type in (DocumentType.TEXT, DocumentType.MARKDOWN) else None
            ),
        )
        return ProcessDocumentIngestionResult(document_id=document_id, status="EMBEDDING_QUEUED")

    async def _load_document(self, document_id: str) -> DocumentModel | None:
        return await self._document_repo.get_by_id(UUID(document_id))

    async def _mark_processing(self, document: DocumentModel) -> None:
        document.mark_processing()
        await self._document_repo.update(document)
        await self._session.commit()

    async def _extract_document(self, document: DocumentModel) -> ExtractedContent:
        if document.type in (DocumentType.TEXT, DocumentType.MARKDOWN):
            if document.raw_content:
                return ExtractedContent(text=document.raw_content, word_count=len(document.raw_content.split()))
            raise DocumentValidationException(
                f"Document {document.id} has type {document.type.value} but no raw_content stored"
            )

        if document.type == DocumentType.URL:
            if not document.source_url:
                raise DocumentValidationException(f"Document {document.id} is type URL but has no source_url")
            return await self._url_extractor.extract_from_url(document.source_url)

        if document.type == DocumentType.YOUTUBE:
            if not document.source_url:
                raise DocumentValidationException(f"Document {document.id} is type YOUTUBE but has no source_url")
            return await self._youtube_extractor.extract_from_url(document.source_url)

        if document.type == DocumentType.PDF:
            if not document.file_path:
                raise DocumentValidationException(f"Document {document.id} is type PDF but has no file_path")
            pdf_bytes = await self._file_storage.read_document_file(document.file_path)
            return await self._pdf_extractor.extract_from_bytes(pdf_bytes, filename=document.file_path)

        raise NotImplementedError(f"Extraction not yet implemented for document type: {document.type.value}.")

    def _build_chunks_data(self, extracted: ExtractedContent) -> list[dict[str, int | str | None]]:
        text_chunks = self._text_chunker.chunk_text(extracted.text)
        if not text_chunks:
            raise DocumentValidationException("Text produced no chunks after splitting")

        page_ranges = _build_page_ranges(extracted.pages)
        return [
            {
                "content": text_chunk.content,
                "chunk_index": text_chunk.chunk_index,
                "start_char": text_chunk.start_char,
                "end_char": text_chunk.end_char,
                "page_number": _page_number_for_span(
                    text_chunk.start_char,
                    text_chunk.end_char,
                    page_ranges,
                ),
                "token_count": text_chunk.token_count,
            }
            for text_chunk in text_chunks
        ]


@dataclass(frozen=True, slots=True)
class _PageRange:
    page_number: int
    start_char: int
    end_char: int


def _build_page_ranges(pages: dict[int, str]) -> list[_PageRange]:
    page_ranges: list[_PageRange] = []
    cursor = 0
    for page_number in sorted(pages):
        text = pages[page_number]
        start_char = cursor
        end_char = start_char + len(text)
        page_ranges.append(_PageRange(page_number=page_number, start_char=start_char, end_char=end_char))
        cursor = end_char + 2
    return page_ranges


def _content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _page_number_for_span(start_char: int, end_char: int, page_ranges: list[_PageRange]) -> int | None:
    if not page_ranges:
        return None
    for page_range in page_ranges:
        if start_char < page_range.end_char and end_char > page_range.start_char:
            return page_range.page_number
    return page_ranges[-1].page_number



@dataclass(frozen=True, slots=True)
class ProcessDocumentEmbeddingsResult:
    document_id: str
    status: str


class DocumentEmbeddingProcessor:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        status_cache: RedisDocumentStatusCache,
        embedding_provider: EmbeddingProvider,
        chunk_repo: ChunkRepository,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._status_cache = status_cache
        self._embedding_provider = embedding_provider
        self._chunk_repo = chunk_repo

    async def __call__(
        self,
        *,
        document_id: str,
        raw_text: str,
        chunks_data: list[dict[str, Any]],
        expected_content_hash: str | None = None,
    ) -> ProcessDocumentEmbeddingsResult:
        document = await self._load_document(document_id)
        if document is None:
            return ProcessDocumentEmbeddingsResult(document_id=document_id, status="NOT_FOUND")
        if _is_stale_text_job(document, expected_content_hash):
            return ProcessDocumentEmbeddingsResult(document_id=document_id, status="STALE")

        await self._status_cache.set_status(
            document.id,
            status="PROCESSING",
            progress=70,
            message="Generating embeddings...",
        )
        document.mark_processing()

        embeddings = await self._embedding_provider.embed_texts(
            [str(chunk["content"]) for chunk in chunks_data]
        )

        await self._status_cache.set_status(
            document.id,
            status="PROCESSING",
            progress=90,
            message="Saving to database...",
        )

        chunk_entities = _build_chunk_entities(document.id, chunks_data, embeddings)
        document.update_content(
            raw_content=document.raw_content or raw_text,
            word_count=len(raw_text.split()),
            language=document.language,
        )
        document.mark_ready()

        await self._chunk_repo.delete_by_document_id(document.id)
        await self._chunk_repo.create_batch(chunk_entities)
        await self._document_repo.update(document)
        await self._session.commit()

        await self._status_cache.set_status(
            document.id,
            status="READY",
            progress=100,
            message="Processing complete.",
        )
        return ProcessDocumentEmbeddingsResult(document_id=document_id, status="READY")

    async def _load_document(self, document_id: str) -> DocumentModel | None:
        return await self._document_repo.get_by_id(UUID(document_id))


def _build_chunk_entities(
    document_id: UUID,
    chunks_data: list[dict[str, Any]],
    embeddings: list[list[float]],
) -> list[ChunkModel]:
    return [
        ChunkModel.create(
            id=uuid.uuid4(),
            document_id=document_id,
            content=str(chunk["content"]),
            embedding=embedding,
            chunk_index=int(chunk["chunk_index"]),
            start_char=_optional_int(chunk.get("start_char")),
            end_char=_optional_int(chunk.get("end_char")),
            page_number=_optional_int(chunk.get("page_number")),
            token_count=_optional_int(chunk.get("token_count")),
        )
        for chunk, embedding in zip(chunks_data, embeddings, strict=True)
    ]


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _is_stale_text_job(document: DocumentModel, expected_content_hash: str | None) -> bool:
    if expected_content_hash is None:
        return False
    current_content = document.raw_content
    if current_content is None:
        return False
    return _content_hash(current_content) != expected_content_hash


@dataclass(frozen=True, slots=True)
class ProcessImageDocumentResult:
    document_id: str
    status: str


class ImageDocumentProcessor:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        status_cache: RedisDocumentStatusCache,
        task_dispatcher: TaskiqTaskDispatcher,
        text_chunker: SimpleTextChunker,
        file_storage: FileStorage,
        image_extractor: ContentExtractor,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._status_cache = status_cache
        self._task_dispatcher = task_dispatcher
        self._text_chunker = text_chunker
        self._file_storage = file_storage
        self._image_extractor = image_extractor

    async def __call__(self, document_id: str) -> ProcessImageDocumentResult:
        document = await self._load_document(document_id)
        if document is None:
            return ProcessImageDocumentResult(document_id=document_id, status="NOT_FOUND")
        if document.type != DocumentType.IMAGE:
            raise DocumentValidationException(f"Document {document.id} is not an IMAGE document")
        if not document.file_path:
            raise DocumentValidationException(f"Document {document.id} is type IMAGE but has no file_path")

        await self._status_cache.set_status(
            document.id,
            status="PROCESSING",
            progress=20,
            message="Running OCR...",
        )
        document.mark_processing()
        await self._document_repo.update(document)
        await self._session.commit()

        image_bytes = await self._file_storage.read_document_file(document.file_path)
        extracted = await self._image_extractor.extract_from_bytes(
            image_bytes,
            filename=document.file_path,
            language=document.language,
        )
        if extracted.visual is not None:
            document.update_visual_metadata(extracted.visual)
            await self._document_repo.update(document)
            await self._session.commit()

        await self._status_cache.set_status(
            document.id,
            status="PROCESSING",
            progress=40,
            message="Splitting OCR text into chunks...",
        )
        prepared_text = _build_image_ingest_text(extracted)
        chunks = self._text_chunker.chunk_text(prepared_text)
        if not chunks:
            raise DocumentValidationException("Image OCR produced no chunks after splitting")

        chunks_data = [
            {
                "content": chunk.content,
                "chunk_index": chunk.chunk_index,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "page_number": None,
                "token_count": chunk.token_count,
            }
            for chunk in chunks
        ]

        await self._status_cache.set_status(
            document.id,
            status="PROCESSING",
            progress=60,
            message="Queued for embedding...",
        )
        await self._task_dispatcher.dispatch_embed_and_finalize_document(
            document_id=document_id,
            raw_text=prepared_text,
            chunks_data=chunks_data,
        )
        return ProcessImageDocumentResult(document_id=document_id, status="EMBEDDING_QUEUED")

    async def _load_document(self, document_id: str) -> DocumentModel | None:
        return await self._document_repo.get_by_id(UUID(document_id))


def _build_image_ingest_text(extracted: ExtractedContent) -> str:
    if not extracted.visual:
        return extracted.text

    layout_type = str(extracted.visual.get("layout_type", "image"))
    block_count = extracted.visual.get("text_block_count", 0)
    line_count = extracted.visual.get("ocr_line_count", 0)
    orientation = extracted.visual.get("orientation", "unknown")
    box_count = _metadata_list_count(extracted.visual.get("diagram_boxes"))
    connector_count = _metadata_list_count(extracted.visual.get("diagram_connectors"))
    relationship_count = _metadata_list_count(extracted.visual.get("diagram_relationships"))
    summary = (
        "Visual summary: "
        f"{layout_type} layout, {orientation} orientation, "
        f"{block_count} text blocks, {line_count} OCR lines, "
        f"{box_count} diagram boxes, {connector_count} connectors, "
        f"{relationship_count} inferred relationships."
    )
    return f"{summary}\n\nOCR transcript:\n{extracted.text}"


def _metadata_list_count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0



class DocumentEnricher:
    def __init__(self, enrichment_service: EnrichmentService) -> None:
        self._enrichment_service = enrichment_service

    async def execute(self, document_id: UUID) -> dict[str, object]:
        result = await self._enrichment_service.enrich_document(document_id)
        return {**result, "document_id": str(document_id)}
