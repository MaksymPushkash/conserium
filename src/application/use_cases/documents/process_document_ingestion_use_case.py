from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from src.application.ports.ingestion.content_extractor import ExtractedContent, IContentExtractor
from src.domain.exceptions import DocumentValidationException
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.file_storage import IFileStorage
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.ingestion.text_chunker import ITextChunker
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.domain.entities.document_entity import DocumentEntity


@dataclass(frozen=True, slots=True)
class ProcessDocumentIngestionResult:
    document_id: str
    status: str


class ProcessDocumentIngestionUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
        text_chunker: ITextChunker,
        file_storage: IFileStorage,
        url_extractor: IContentExtractor,
        youtube_extractor: IContentExtractor,
        pdf_extractor: IContentExtractor,
    ) -> None:
        self._uow = uow
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

    async def _load_document(self, document_id: str) -> DocumentEntity | None:
        async with self._uow:
            return await self._uow.document_repo.get_by_id(UUID(document_id))

    async def _mark_processing(self, document: DocumentEntity) -> None:
        document.mark_processing()
        async with self._uow:
            await self._uow.document_repo.update(document)
            await self._uow.commit()

    async def _extract_document(self, document: DocumentEntity) -> ExtractedContent:
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
