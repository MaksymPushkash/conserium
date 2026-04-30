import uuid

from src.application.dtos.document_dtos import DocumentDTO
from src.application.dtos.ingestion_dtos import IngestTextDocumentDTO
from src.application.ports.ingestion.text_chunker import ITextChunker
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.base import document_to_dto
from src.domain.entities.chunk_entity import ChunkEntity
from src.domain.entities.document_entity import DocumentEntity


class IngestTextDocumentUseCase:
    def __init__(self, uow: IUnitOfWork, text_chunker: ITextChunker) -> None:
        self._uow = uow
        self._text_chunker = text_chunker

    async def __call__(self, dto: IngestTextDocumentDTO) -> DocumentDTO:
        if not dto.raw_text.strip():
            raise ValueError("raw_text cannot be empty")

        document = DocumentEntity.create(
            id=uuid.uuid4(),
            user_id=dto.user_id,
            collection_id=dto.collection_id,
            title=dto.title,
            type=dto.type,
            source_url=dto.source_url,
            file_size_bytes=len(dto.raw_text.encode()),
            raw_content=dto.raw_text,
            word_count=len(dto.raw_text.split()),
            language=dto.language,
        )

        async with self._uow:
            await self._uow.document_repo.create(document)

            text_chunks = self._text_chunker.chunk_text(dto.raw_text)
            if not text_chunks:
                raise ValueError("raw_text produced no chunks")

            chunks = [
                ChunkEntity.create(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    content=text_chunk.content,
                    embedding=[0.0] * ChunkEntity.EMBEDDING_DIMENSIONS,
                    chunk_index=text_chunk.chunk_index,
                    start_char=text_chunk.start_char,
                    end_char=text_chunk.end_char,
                    token_count=text_chunk.token_count,
                )
                for text_chunk in text_chunks
            ]

            await self._uow.chunk_repo.create_batch(chunks)
            document.mark_ready()
            await self._uow.document_repo.update(document)
            await self._uow.commit()

        return document_to_dto(document)
