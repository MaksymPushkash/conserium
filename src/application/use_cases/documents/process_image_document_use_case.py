from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from src.domain.exceptions import DocumentValidationException
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.content_extractor import ExtractedContent, IContentExtractor
    from src.application.ports.ingestion.file_storage import IFileStorage
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.ingestion.text_chunker import ITextChunker
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.domain.entities.document_entity import DocumentEntity


@dataclass(frozen=True, slots=True)
class ProcessImageDocumentResult:
    document_id: str
    status: str


class ProcessImageDocumentUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
        text_chunker: ITextChunker,
        file_storage: IFileStorage,
        image_extractor: IContentExtractor,
    ) -> None:
        self._uow = uow
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
        async with self._uow:
            await self._uow.document_repo.update(document)
            await self._uow.commit()

        image_bytes = await self._file_storage.read_document_file(document.file_path)
        extracted = await self._image_extractor.extract_from_bytes(
            image_bytes,
            filename=document.file_path,
            language=document.language,
        )
        if extracted.visual is not None:
            document.update_visual_metadata(extracted.visual)
            async with self._uow:
                await self._uow.document_repo.update(document)
                await self._uow.commit()

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

    async def _load_document(self, document_id: str) -> DocumentEntity | None:
        async with self._uow:
            return await self._uow.document_repo.get_by_id(UUID(document_id))


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
