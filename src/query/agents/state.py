from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from src.documents.types import DocumentType
from src.query.schemas import ConversationTurnDTO, QuerySourceDTO, RefragContextPackage


class QueryType(StrEnum):
    SEARCH = "search"
    SUMMARY = "summary"
    DOCUMENT_QA = "document_qa"
    GENERAL = "general"


@dataclass(slots=True)
class ConseriumQueryState:
    query: str
    user_id: UUID
    limit: int
    conversation_id: UUID
    collection_id: UUID | None = None
    tag_names: tuple[str, ...] | None = None
    document_types: tuple[DocumentType, ...] | None = None
    document_ids: tuple[UUID, ...] | None = None
    conversation_turns: list[ConversationTurnDTO] = field(default_factory=list)
    retrieval_query: str | None = None
    relevance_query: str | None = None
    answer_language: str = "match_question"
    retrieval_depth: str = "balanced"
    promoted_document_ids: list[UUID] = field(default_factory=list)
    query_type: QueryType = QueryType.SEARCH
    sources: list[QuerySourceDTO] = field(default_factory=list)
    retrieved_sources: list[QuerySourceDTO] = field(default_factory=list)
    filtered_sources: list[QuerySourceDTO] = field(default_factory=list)
    refrag_context: RefragContextPackage | None = None
    answer: str = ""
    eval_scores: dict[str, float] = field(default_factory=dict)
    trace_id: str | None = None


def coerce_conserium_query_state(value: ConseriumQueryState | Mapping[str, Any]) -> ConseriumQueryState:
    if isinstance(value, ConseriumQueryState):
        return value

    query_type = value.get("query_type", QueryType.SEARCH)
    return ConseriumQueryState(
        query=cast("str", value["query"]),
        user_id=cast("UUID", value["user_id"]),
        limit=cast("int", value["limit"]),
        conversation_id=cast("UUID", value["conversation_id"]),
        collection_id=cast("UUID | None", value.get("collection_id")),
        tag_names=cast("tuple[str, ...] | None", value.get("tag_names")),
        document_types=cast("tuple[DocumentType, ...] | None", value.get("document_types")),
        document_ids=cast("tuple[UUID, ...] | None", value.get("document_ids")),
        conversation_turns=cast("list[ConversationTurnDTO]", value.get("conversation_turns", [])),
        retrieval_query=cast("str | None", value.get("retrieval_query")),
        relevance_query=cast("str | None", value.get("relevance_query")),
        answer_language=cast("str", value.get("answer_language", "match_question")),
        retrieval_depth=cast("str", value.get("retrieval_depth", "balanced")),
        promoted_document_ids=cast("list[UUID]", value.get("promoted_document_ids", [])),
        query_type=query_type if isinstance(query_type, QueryType) else QueryType(query_type),
        sources=cast("list[QuerySourceDTO]", value.get("sources", [])),
        retrieved_sources=cast("list[QuerySourceDTO]", value.get("retrieved_sources", [])),
        filtered_sources=cast("list[QuerySourceDTO]", value.get("filtered_sources", [])),
        refrag_context=cast("RefragContextPackage | None", value.get("refrag_context")),
        answer=cast("str", value.get("answer", "")),
        eval_scores=cast("dict[str, float]", value.get("eval_scores", {})),
        trace_id=cast("str | None", value.get("trace_id")),
    )
