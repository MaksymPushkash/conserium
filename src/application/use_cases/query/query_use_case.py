from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog

from src.application.agents.query.state import CortexQueryState
from src.application.dtos.query_dtos import QueryResultDTO
from src.application.services.query_orchestration import (
    QueryOrchestrationService,
    mark_sources_used_in_answer,
    query_debug,
    refrag_context_payload,
)
from src.domain.exceptions import QueryProcessingException, QueryValidationException

if TYPE_CHECKING:
    from src.application.agents.query.graph_runner import QueryGraphRunner
    from src.application.dtos.query_dtos import QueryDTO
    from src.application.ports.conversations.conversation_store import IConversationStore
    from src.application.ports.persistence.unit_of_work import IUnitOfWork

logger = structlog.get_logger(__name__)


class QueryUseCase:
    RECENT_TURN_LIMIT = 6

    def __init__(
        self,
        graph_runner: QueryGraphRunner,
        conversation_store: IConversationStore,
        uow: IUnitOfWork,
    ) -> None:
        self._graph_runner = graph_runner
        self._orchestration = QueryOrchestrationService(conversation_store, uow)

    async def __call__(self, dto: QueryDTO) -> QueryResultDTO:
        query = dto.query.strip()
        if not query:
            raise QueryValidationException("query cannot be empty")

        conversation_id = dto.conversation_id or uuid4()
        conversation_turns = await self._orchestration.prepare_context(dto, query=query, conversation_id=conversation_id)
        started_at = perf_counter()
        state = await self._graph_runner.run(
            CortexQueryState(
                query=query,
                user_id=dto.user_id,
                limit=dto.limit,
                conversation_id=conversation_id,
                collection_id=dto.collection_id,
                tag_names=dto.tag_names,
                document_types=dto.document_types,
                conversation_turns=conversation_turns,
            )
        )
        latency_ms = int((perf_counter() - started_at) * 1000)
        if state.refrag_context is None:
            raise QueryProcessingException("query graph did not produce refrag_context")
        state.sources = mark_sources_used_in_answer(state.sources, state.answer)
        debug = query_debug(query, state)
        await self._orchestration.append_turn(
            user_id=dto.user_id,
            conversation_id=conversation_id,
            query=query,
            answer=state.answer,
            sources=state.sources,
        )
        await self._orchestration.record_interaction(
            dto,
            query=query,
            state=state,
            latency_ms=latency_ms,
            conversation_id=conversation_id,
            refrag_context=refrag_context_payload(state.refrag_context),
        )
        logger.info(
            "query_completed",
            mode="sync",
            trace_id=state.trace_id,
            conversation_id=str(conversation_id),
            collection_id=str(dto.collection_id) if dto.collection_id else None,
            sources=len(state.sources),
            used_sources=sum(1 for source in state.sources if source.used_in_answer),
            latency_ms=latency_ms,
        )
        return QueryResultDTO(
            conversation_id=conversation_id,
            query=query,
            answer=state.answer,
            sources=state.sources,
            refrag_context=state.refrag_context,
            debug=debug,
        )
