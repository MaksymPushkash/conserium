from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from src.application.dtos.conversation_dtos import ConversationTurnDTO
from src.application.dtos.query_dtos import QuerySourceDTO
from src.application.dtos.refrag_dtos import RefragContextPackage


class QueryType(StrEnum):
    SEARCH = "search"
    SUMMARY = "summary"
    DOCUMENT_QA = "document_qa"
    GENERAL = "general"


@dataclass(slots=True)
class CortexQueryState:
    query: str
    user_id: UUID
    limit: int
    conversation_id: UUID
    collection_id: UUID | None = None
    conversation_turns: list[ConversationTurnDTO] = field(default_factory=list)
    retrieval_query: str | None = None
    promoted_document_ids: list[UUID] = field(default_factory=list)
    query_type: QueryType = QueryType.SEARCH
    sources: list[QuerySourceDTO] = field(default_factory=list)
    refrag_context: RefragContextPackage | None = None
    answer: str = ""


def coerce_cortex_query_state(value: CortexQueryState | Mapping[str, Any]) -> CortexQueryState:
    if isinstance(value, CortexQueryState):
        return value

    query_type = value.get("query_type", QueryType.SEARCH)
    return CortexQueryState(
        query=cast("str", value["query"]),
        user_id=cast("UUID", value["user_id"]),
        limit=cast("int", value["limit"]),
        conversation_id=cast("UUID", value["conversation_id"]),
        collection_id=cast("UUID | None", value.get("collection_id")),
        conversation_turns=cast("list[ConversationTurnDTO]", value.get("conversation_turns", [])),
        retrieval_query=cast("str | None", value.get("retrieval_query")),
        promoted_document_ids=cast("list[UUID]", value.get("promoted_document_ids", [])),
        query_type=query_type if isinstance(query_type, QueryType) else QueryType(query_type),
        sources=cast("list[QuerySourceDTO]", value.get("sources", [])),
        refrag_context=cast("RefragContextPackage | None", value.get("refrag_context")),
        answer=cast("str", value.get("answer", "")),
    )
