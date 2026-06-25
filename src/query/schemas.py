from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, final
from uuid import UUID

from pydantic import BaseModel, Field

from src.documents.types import DocumentType
from src.public_shares.schemas import PublicAnswerShareResponse


class RefragRepresentation(StrEnum):
    FULL_TEXT = "FULL_TEXT"
    COMPRESSED = "COMPRESSED"
    DISCARDED = "DISCARDED"


@final
@dataclass(frozen=True, slots=True)
class RefragChunk:
    chunk_id: UUID
    document_id: UUID
    document_title: str | None
    original_text: str
    context_text: str
    representation: RefragRepresentation
    page_number: int | None
    chunk_index: int
    score: float | None
    original_token_count: int
    context_token_count: int


@final
@dataclass(frozen=True, slots=True)
class RefragContextPackage:
    query: str
    full_text_chunks: list[RefragChunk]
    compressed_chunks: list[RefragChunk]
    discarded_chunks: list[RefragChunk]
    total_original_tokens: int
    total_context_tokens: int
    compression_strategy: str

    @property
    def selected_chunks(self) -> list[RefragChunk]:
        return [*self.full_text_chunks, *self.compressed_chunks]


@final
@dataclass(frozen=True, slots=True)
class QueryPayload:
    user_id: UUID
    query: str
    retrieval_query: str | None = None
    relevance_query: str | None = None
    answer_language: str = "match_question"
    retrieval_depth: str = "balanced"
    conversation_id: UUID | None = None
    collection_id: UUID | None = None
    tag_names: tuple[str, ...] | None = None
    document_types: tuple[DocumentType, ...] | None = None
    document_ids: tuple[UUID, ...] | None = None
    limit: int = 5


@final
@dataclass(frozen=True, slots=True)
class QuerySource:
    chunk_id: UUID
    document_id: UUID
    document_title: str | None
    content: str
    page_number: int | None
    chunk_index: int
    score: float | None = None
    used_in_answer: bool = False


@final
@dataclass(frozen=True, slots=True)
class QueryDebug:
    original_query: str
    retrieval_query: str
    selected_collection_id: UUID | None
    selected_tags: list[str]
    promoted_document_ids: list[UUID]
    retrieved_sources: list[QuerySource]
    final_sources: list[QuerySource]
    used_sources: list[QuerySource]
    filtered_sources: list[QuerySource]


@final
@dataclass(frozen=True, slots=True)
class QueryResult:
    conversation_id: UUID
    query: str
    answer: str
    sources: list[QuerySource]
    refrag_context: RefragContextPackage
    debug: QueryDebug | None = None
    suggested_follow_up_questions: list[str] = field(default_factory=list)


@final
@dataclass(frozen=True, slots=True)
class ConversationSource:
    chunk_id: UUID
    document_id: UUID
    document_title: str | None
    page_number: int | None
    chunk_index: int
    score: float | None


@final
@dataclass(frozen=True, slots=True)
class ConversationTurn:
    query: str
    answer: str
    sources: list[ConversationSource]
    created_at: datetime


@final
@dataclass(frozen=True, slots=True)
class QueryEvaluationRecord:
    user_id: UUID
    collection_id: UUID | None
    document_ids: tuple[UUID, ...]
    query_text: str
    query_type: str
    result_count: int
    answer_text: str
    latency_ms: int | None
    ragas_faithfulness: float | None
    ragas_answer_relevancy: float | None
    ragas_context_recall: float | None
    langfuse_trace_id: str | None


class QueryStreamEventType(StrEnum):
    METADATA = "metadata"
    TOKEN = "token"
    SOURCES = "sources"
    REFRAG_CONTEXT = "refrag_context"
    DEBUG = "debug"
    DONE = "done"
    ERROR = "error"


@final
@dataclass(frozen=True, slots=True)
class QueryStreamEvent:
    event: QueryStreamEventType
    data: dict[str, Any]


@final
@dataclass(frozen=True, slots=True)
class QueryStreamMetadata:
    query_id: UUID
    query: str
    source_count: int


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
    suggested_follow_up_questions: list[str] = Field(default_factory=list)


class PublicQuerySourceResponse(BaseModel):
    document_title: str | None
    content: str
    page_number: int | None
    chunk_index: int
    citation: str
    used_in_answer: bool = False


class PublicCollectionQueryResponse(BaseModel):
    query: str
    answer: str
    sources: list[PublicQuerySourceResponse]
    suggested_follow_up_questions: list[str] = Field(default_factory=list)
    share: PublicAnswerShareResponse
