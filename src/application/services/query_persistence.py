from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.dtos.evaluation_dtos import QueryEvaluationRecordDTO
from src.application.services.query_activity_recorder import record_document_activity
from src.application.services.query_payloads import source_payload

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from src.application.agents.query.state import CortexQueryState
    from src.application.dtos.query_dtos import QueryDTO, QuerySourceDTO
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class QueryPersistenceService:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def record_query(self, dto: QueryDTO, query: str, state: CortexQueryState, latency_ms: int) -> None:
        async with self._uow:
            await self._record_query(dto, query, state, latency_ms)
            await self._uow.commit()

    async def record_chat_messages(
        self,
        *,
        conversation_id: UUID,
        query: str,
        answer: str,
        sources: list[QuerySourceDTO],
        refrag_context: dict[str, object],
        eval_scores: Mapping[str, object],
        trace_id: str | None,
    ) -> None:
        async with self._uow:
            await self._uow.chat_repo.append_message(chat_id=conversation_id, role="user", content=query)
            await self._uow.chat_repo.append_message(
                chat_id=conversation_id,
                role="assistant",
                content=answer,
                sources=[source_payload(source) for source in sources],
                refrag_context=refrag_context,
                eval_scores=dict(eval_scores),
                trace_id=trace_id,
            )
            await self._uow.commit()

    async def record_interaction(
        self,
        dto: QueryDTO,
        *,
        query: str,
        state: CortexQueryState,
        latency_ms: int,
        refrag_context: dict[str, object],
        conversation_id: UUID,
    ) -> None:
        async with self._uow:
            await self._record_query(dto, query, state, latency_ms)
            await self._uow.chat_repo.append_message(chat_id=conversation_id, role="user", content=query)
            await self._uow.chat_repo.append_message(
                chat_id=conversation_id,
                role="assistant",
                content=state.answer,
                sources=[source_payload(source) for source in state.sources],
                refrag_context=refrag_context,
                eval_scores=dict(state.eval_scores),
                trace_id=state.trace_id,
            )
            await record_document_activity(self._uow, dto.user_id, state.sources)
            await self._uow.commit()

    async def _record_query(self, dto: QueryDTO, query: str, state: CortexQueryState, latency_ms: int) -> None:
        await self._uow.search_query_repo.record_query(
            QueryEvaluationRecordDTO(
                user_id=dto.user_id,
                collection_id=dto.collection_id,
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
