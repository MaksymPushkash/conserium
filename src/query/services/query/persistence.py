from __future__ import annotations

from typing import TYPE_CHECKING

from src.query.schemas import QueryEvaluationRecord
from src.query.services.query.activity_recorder import record_document_activity
from src.query.services.query.payloads import source_payload

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from src.chats.repository import ChatRepository
    from src.documents.activity_repository import DocumentActivityRepository
    from src.postgres import AsyncSession
    from src.query.agents.state import ConseriumQueryState
    from src.query.repository import SearchQueryRepository
    from src.query.schemas import QueryInput, QuerySource


class QueryPersistenceService:
    def __init__(
        self,
        session: AsyncSession,
        chat_repo: ChatRepository,
        document_activity_repo: DocumentActivityRepository,
        search_query_repo: SearchQueryRepository,
    ) -> None:
        self._session = session
        self._chat_repo = chat_repo
        self._document_activity_repo = document_activity_repo
        self._search_query_repo = search_query_repo

    async def record_query(self, dto: QueryInput, query: str, state: ConseriumQueryState, latency_ms: int) -> None:
        await self._record_query(dto, query, state, latency_ms)
        await self._session.flush()

    async def record_chat_messages(
        self,
        *,
        conversation_id: UUID,
        query: str,
        answer: str,
        sources: list[QuerySource],
        refrag_context: dict[str, object],
        eval_scores: Mapping[str, object],
        trace_id: str | None,
    ) -> None:
        await self._chat_repo.append_message(chat_id=conversation_id, role="user", content=query)
        await self._chat_repo.append_message(
            chat_id=conversation_id,
            role="assistant",
            content=answer,
            sources=[source_payload(source) for source in sources],
            refrag_context=refrag_context,
            eval_scores=dict(eval_scores),
            trace_id=trace_id,
        )
        await self._session.flush()

    async def record_interaction(
        self,
        dto: QueryInput,
        *,
        query: str,
        state: ConseriumQueryState,
        latency_ms: int,
        refrag_context: dict[str, object],
        conversation_id: UUID,
    ) -> None:
        await self._record_query(dto, query, state, latency_ms)
        await self._chat_repo.append_message(chat_id=conversation_id, role="user", content=query)
        await self._chat_repo.append_message(
            chat_id=conversation_id,
            role="assistant",
            content=state.answer,
            sources=[source_payload(source) for source in state.sources],
            refrag_context=refrag_context,
            eval_scores=dict(state.eval_scores),
            trace_id=state.trace_id,
        )
        await record_document_activity(self._document_activity_repo, dto.user_id, state.sources)
        await self._session.flush()

    async def _record_query(self, dto: QueryInput, query: str, state: ConseriumQueryState, latency_ms: int) -> None:
        await self._search_query_repo.record_query(
            QueryEvaluationRecord(
                user_id=dto.user_id,
                collection_id=dto.collection_id,
                document_ids=_query_document_ids(dto, state),
                query_text=query,
                query_type=state.query_type.value,
                result_count=len(state.sources),
                answer_text=state.answer,
                latency_ms=latency_ms,
                ragas_faithfulness=state.eval_scores.get("faithfulness"),
                ragas_answer_relevancy=state.eval_scores.get("answer_relevancy"),
                ragas_context_recall=state.eval_scores.get("context_recall"),
                langfuse_trace_id=state.trace_id,
            )
        )


def _query_document_ids(dto: QueryInput, state: ConseriumQueryState) -> tuple[UUID, ...]:
    if dto.document_ids:
        return dto.document_ids
    seen: set[UUID] = set()
    document_ids: list[UUID] = []
    for source in state.sources:
        if source.document_id not in seen:
            seen.add(source.document_id)
            document_ids.append(source.document_id)
    return tuple(document_ids)
