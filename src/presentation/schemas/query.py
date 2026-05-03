from uuid import UUID

from pydantic import BaseModel, Field

from src.application.dtos.query_dtos import QueryResultDTO, QuerySourceDTO
from src.application.dtos.refrag_dtos import RefragChunk, RefragContextPackage, RefragRepresentation
from src.domain.value_objects.document_type import DocumentType


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    conversation_id: UUID | None = None
    collection_id: UUID | None = None
    document_types: list[DocumentType] | None = None
    limit: int = Field(default=5, ge=1, le=20)


class QuerySourceResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str | None
    content: str
    page_number: int | None
    chunk_index: int
    score: float | None
    citation: str

    @classmethod
    def from_dto(cls, dto: QuerySourceDTO, index: int) -> "QuerySourceResponse":
        return cls(
            chunk_id=dto.chunk_id,
            document_id=dto.document_id,
            document_title=dto.document_title,
            content=dto.content,
            page_number=dto.page_number,
            chunk_index=dto.chunk_index,
            score=dto.score,
            citation=f"[{index}]",
        )


class RefragChunkResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str | None
    representation: RefragRepresentation
    page_number: int | None
    chunk_index: int
    score: float | None
    context_text: str
    original_token_count: int
    context_token_count: int
    citation: str | None

    @classmethod
    def from_dto(cls, dto: RefragChunk, citation: str | None) -> "RefragChunkResponse":
        return cls(
            chunk_id=dto.chunk_id,
            document_id=dto.document_id,
            document_title=dto.document_title,
            representation=dto.representation,
            page_number=dto.page_number,
            chunk_index=dto.chunk_index,
            score=dto.score,
            context_text=dto.context_text,
            original_token_count=dto.original_token_count,
            context_token_count=dto.context_token_count,
            citation=citation,
        )


class RefragContextResponse(BaseModel):
    full_text_chunks: list[RefragChunkResponse]
    compressed_chunks: list[RefragChunkResponse]
    discarded_chunks: list[RefragChunkResponse]
    total_original_tokens: int
    total_context_tokens: int
    compression_strategy: str

    @classmethod
    def from_dto(cls, dto: RefragContextPackage) -> "RefragContextResponse":
        full_text_chunks = [
            RefragChunkResponse.from_dto(chunk, f"[{index}]")
            for index, chunk in enumerate(dto.full_text_chunks, start=1)
        ]
        compressed_start = len(dto.full_text_chunks) + 1
        compressed_chunks = [
            RefragChunkResponse.from_dto(chunk, f"[{index}]")
            for index, chunk in enumerate(dto.compressed_chunks, start=compressed_start)
        ]
        discarded_chunks = [RefragChunkResponse.from_dto(chunk, None) for chunk in dto.discarded_chunks]
        return cls(
            full_text_chunks=full_text_chunks,
            compressed_chunks=compressed_chunks,
            discarded_chunks=discarded_chunks,
            total_original_tokens=dto.total_original_tokens,
            total_context_tokens=dto.total_context_tokens,
            compression_strategy=dto.compression_strategy,
        )


class QueryResponse(BaseModel):
    conversation_id: UUID
    query: str
    answer: str
    sources: list[QuerySourceResponse]
    refrag_context: RefragContextResponse

    @classmethod
    def from_dto(cls, dto: QueryResultDTO) -> "QueryResponse":
        return cls(
            conversation_id=dto.conversation_id,
            query=dto.query,
            answer=dto.answer,
            sources=[QuerySourceResponse.from_dto(source, index) for index, source in enumerate(dto.sources, start=1)],
            refrag_context=RefragContextResponse.from_dto(dto.refrag_context),
        )
