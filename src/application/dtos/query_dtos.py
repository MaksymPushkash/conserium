from dataclasses import dataclass
from typing import final
from uuid import UUID

from src.application.dtos.refrag_dtos import RefragContextPackage
from src.domain.value_objects.document_type import DocumentType


@final
@dataclass(frozen=True, slots=True)
class QueryDTO:
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
class QuerySourceDTO:
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
class QueryDebugDTO:
    original_query: str
    retrieval_query: str
    selected_collection_id: UUID | None
    selected_tags: list[str]
    promoted_document_ids: list[UUID]
    retrieved_sources: list[QuerySourceDTO]
    final_sources: list[QuerySourceDTO]
    used_sources: list[QuerySourceDTO]
    filtered_sources: list[QuerySourceDTO]


@final
@dataclass(frozen=True, slots=True)
class QueryResultDTO:
    conversation_id: UUID
    query: str
    answer: str
    sources: list[QuerySourceDTO]
    refrag_context: RefragContextPackage
    debug: QueryDebugDTO | None = None
