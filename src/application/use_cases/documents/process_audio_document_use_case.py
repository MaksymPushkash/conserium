from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.content_extractor import IContentExtractor
    from src.application.ports.ingestion.file_storage import IFileStorage
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.ingestion.text_chunker import ITextChunker
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.domain.entities.document_entity import DocumentEntity


@dataclass(frozen=True, slots=True)
class ProcessAudioDocumentResult:
    document_id: str
    status: str


class ProcessAudioDocumentUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
        text_chunker: ITextChunker,
        file_storage: IFileStorage,
        audio_extractor: IContentExtractor,
    ) -> None:
        self._uow = uow
        self._status_cache = status_cache
        self._task_dispatcher = task_dispatcher
        self._text_chunker = text_chunker
        self._file_storage = file_storage
        self._audio_extractor = audio_extractor

    async def __call__(self, document_id: str) -> ProcessAudioDocumentResult:
        document = await self._load_document(document_id)
        if document is None:
            return ProcessAudioDocumentResult(document_id=document_id, status="NOT_FOUND")
        if document.type != DocumentType.AUDIO:
            raise ValueError(f"Document {document.id} is not an AUDIO document")
        if not document.file_path:
            raise ValueError(f"Document {document.id} is type AUDIO but has no file_path")

        await self._status_cache.set_status(
            document.id,
            status="PROCESSING",
            progress=20,
            message="Transcribing audio...",
        )
        document.mark_processing()
        async with self._uow:
            await self._uow.document_repo.update(document)
            await self._uow.commit()

        audio_bytes = await self._file_storage.read_document_file(document.file_path)
        extracted = await self._audio_extractor.extract_from_bytes(
            audio_bytes,
            filename=document.file_path,
            language=document.language,
        )

        await self._status_cache.set_status(
            document.id,
            status="PROCESSING",
            progress=40,
            message="Splitting transcript into chunks...",
        )
        chunks = self._text_chunker.chunk_text(extracted.text)
        if not chunks:
            raise ValueError("Audio transcription produced no chunks after splitting")

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
            raw_text=extracted.text,
            chunks_data=chunks_data,
        )
        return ProcessAudioDocumentResult(document_id=document_id, status="EMBEDDING_QUEUED")

    async def _load_document(self, document_id: str) -> DocumentEntity | None:
        async with self._uow:
            return await self._uow.document_repo.get_by_id(UUID(document_id))
