from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog

from src.application.agents.query.state import CortexQueryState
from src.application.dtos.query_stream_dtos import QueryStreamEventDTO, QueryStreamEventType
from src.application.services.query_orchestration import QueryOrchestrationService
from src.application.services.query_payloads import (
    mark_sources_used_in_answer,
    query_debug_payload,
    refrag_context_payload,
    stream_metadata_payload,
    stream_refrag_context_payload,
    stream_sources_payload,
)
from src.domain.exceptions import QueryProcessingException

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from src.application.agents.query.streaming_graph_runner import StreamingQueryGraphRunner
    from src.application.dtos.query_dtos import QueryDTO
    from src.application.ports.conversations.conversation_store import IConversationStore
    from src.application.ports.persistence.unit_of_work import IUnitOfWork

logger = structlog.get_logger(__name__)


class StreamQueryUseCase:
    RECENT_TURN_LIMIT = 6

    def __init__(
        self,
        graph_runner: StreamingQueryGraphRunner,
        conversation_store: IConversationStore,
        uow: IUnitOfWork,
    ) -> None:
        self._graph_runner = graph_runner
        self._orchestration = QueryOrchestrationService(conversation_store, uow)

    async def __call__(self, dto: QueryDTO) -> AsyncIterator[QueryStreamEventDTO]:
        query = dto.query.strip()
        if not query:
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.ERROR,
                data={"message": "query cannot be empty"},
            )
            return

        query_id = uuid4()
        conversation_id = dto.conversation_id or uuid4()
        started_at = perf_counter()
        try:
            conversation_turns = await self._orchestration.prepare_context(dto, query=query, conversation_id=conversation_id)
            state = await self._graph_runner.prepare(
                CortexQueryState(
                    query=query,
                    user_id=dto.user_id,
                    limit=dto.limit,
                    conversation_id=conversation_id,
                    collection_id=dto.collection_id,
                    tag_names=dto.tag_names,
                    document_types=dto.document_types,
                    document_ids=dto.document_ids,
                    conversation_turns=conversation_turns,
                    retrieval_query=dto.retrieval_query.strip() if dto.retrieval_query is not None else None,
                    relevance_query=dto.relevance_query.strip() if dto.relevance_query is not None else None,
                    answer_language=dto.answer_language,
                    retrieval_depth=dto.retrieval_depth,
                )
            )
            if state.refrag_context is None:
                raise QueryProcessingException("query graph did not produce refrag_context")

            yield QueryStreamEventDTO(
                event=QueryStreamEventType.METADATA,
                data=stream_metadata_payload(query_id, conversation_id, query, state.sources),
            )

            answer_parts: list[str] = []
            async for token in self._graph_runner.stream_answer(state):
                if token:
                    answer_parts.append(token)
                    yield QueryStreamEventDTO(
                        event=QueryStreamEventType.TOKEN,
                        data={"text": token},
                    )

            state.answer = "".join(answer_parts)
            state.sources = mark_sources_used_in_answer(state.sources, state.answer)
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.DEBUG,
                data=query_debug_payload(query, state),
            )
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.SOURCES,
                data=stream_sources_payload(state.sources),
            )
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.REFRAG_CONTEXT,
                data=stream_refrag_context_payload(state.refrag_context),
            )
            await self._orchestration.append_turn(
                user_id=dto.user_id,
                conversation_id=conversation_id,
                query=query,
                answer=state.answer,
                sources=state.sources,
            )
            state = await self._graph_runner.evaluate(state)
            latency_ms = int((perf_counter() - started_at) * 1000)
            if state.refrag_context is None:
                raise QueryProcessingException("query graph did not produce refrag_context")
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
                mode="stream",
                trace_id=state.trace_id,
                conversation_id=str(conversation_id),
                collection_id=str(dto.collection_id) if dto.collection_id else None,
                sources=len(state.sources),
                used_sources=sum(1 for source in state.sources if source.used_in_answer),
                latency_ms=latency_ms,
            )
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.DONE,
                data={
                    "query_id": str(query_id),
                    "conversation_id": str(conversation_id),
                    "eval_scores": state.eval_scores,
                    "trace_id": state.trace_id,
                },
            )
        except Exception as exc:
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.ERROR,
                data={"query_id": str(query_id), "conversation_id": str(conversation_id), "message": str(exc)},
            )
