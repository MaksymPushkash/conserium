from uuid import UUID

from pydantic import BaseModel, Field

from src.application.dtos.refrag_dtos import RefragRepresentation
from src.domain.value_objects.document_type import DocumentType


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None
    collection_id: UUID | None = None
    document_id: UUID | None = None
    tag_names: list[str] | None = Field(default=None, max_length=20)
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
    used_in_answer: bool = False


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


class RefragContextResponse(BaseModel):
    full_text_chunks: list[RefragChunkResponse]
    compressed_chunks: list[RefragChunkResponse]
    discarded_chunks: list[RefragChunkResponse]
    total_original_tokens: int
    total_context_tokens: int
    compression_strategy: str


class QueryDebugResponse(BaseModel):
    original_query: str
    retrieval_query: str
    selected_collection_id: UUID | None
    selected_tags: list[str]
    promoted_document_ids: list[UUID]
    retrieved_sources: list[QuerySourceResponse]
    final_sources: list[QuerySourceResponse]
    used_sources: list[QuerySourceResponse]
    filtered_sources: list[QuerySourceResponse]


class QueryResponse(BaseModel):
    conversation_id: UUID
    query: str
    answer: str
    sources: list[QuerySourceResponse]
    refrag_context: RefragContextResponse
    debug: QueryDebugResponse | None = None
