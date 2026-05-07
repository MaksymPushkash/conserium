from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.application.agents.query.state import CortexQueryState
from src.application.dtos.conversation_dtos import ConversationSourceDTO, ConversationTurnDTO
from src.application.dtos.evaluation_dtos import QueryEvaluationRecordDTO
from src.application.dtos.query_stream_dtos import QueryStreamEventDTO, QueryStreamEventType
from src.application.use_cases.query.query_use_case import _refrag_context_payload, _source_payload, _title_from_query
from src.core.config import settings
from src.domain.exceptions import QueryProcessingException

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from src.application.agents.query.streaming_graph_runner import StreamingQueryGraphRunner
    from src.application.dtos.query_dtos import QueryDTO, QuerySourceDTO
    from src.application.dtos.refrag_dtos import RefragChunk
    from src.application.ports.conversations.conversation_store import IConversationStore
    from src.application.ports.persistence.chat_repository import IChatRepository
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class StreamQueryUseCase:
    RECENT_TURN_LIMIT = 6

    def __init__(
        self,
        graph_runner: StreamingQueryGraphRunner,
        conversation_store: IConversationStore,
        uow: IUnitOfWork,
    ) -> None:
        self._graph_runner = graph_runner
        self._conversation_store = conversation_store
        self._uow = uow

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
            await self._ensure_chat_session(user_id=dto.user_id, conversation_id=conversation_id, title=query)
            conversation_turns = await self._conversation_store.get_recent_turns(
                user_id=dto.user_id,
                conversation_id=conversation_id,
                limit=self.RECENT_TURN_LIMIT,
            )
            if not conversation_turns:
                conversation_turns = await self._get_persisted_recent_turns(
                    user_id=dto.user_id,
                    conversation_id=conversation_id,
                )
            state = await self._graph_runner.prepare(
                CortexQueryState(
                    query=query,
                    user_id=dto.user_id,
                    limit=dto.limit,
                    conversation_id=conversation_id,
                    collection_id=dto.collection_id,
                    document_types=dto.document_types,
                    conversation_turns=conversation_turns,
                )
            )
            if state.refrag_context is None:
                raise QueryProcessingException("query graph did not produce refrag_context")

            yield QueryStreamEventDTO(
                event=QueryStreamEventType.METADATA,
                data={
                    "query_id": str(query_id),
                    "conversation_id": str(conversation_id),
                    "query": query,
                    "sources": [
                        {
                            "citation": f"[{index}]",
                            "chunk_id": str(source.chunk_id),
                            "document_id": str(source.document_id),
                            "document_title": source.document_title,
                            "page_number": source.page_number,
                            "chunk_index": source.chunk_index,
                            "score": source.score,
                        }
                        for index, source in enumerate(state.sources, start=1)
                    ],
                },
            )

            answer_parts: list[str] = []
            async for token in self._graph_runner.stream_answer(state):
                if token:
                    answer_parts.append(token)
                    yield QueryStreamEventDTO(
                        event=QueryStreamEventType.TOKEN,
                        data={"text": token},
                    )

            yield QueryStreamEventDTO(
                event=QueryStreamEventType.SOURCES,
                data={
                    "sources": [
                        {
                            "citation": f"[{index}]",
                            "chunk_id": str(source.chunk_id),
                            "document_id": str(source.document_id),
                            "document_title": source.document_title,
                            "content": source.content,
                            "page_number": source.page_number,
                            "chunk_index": source.chunk_index,
                            "score": source.score,
                        }
                        for index, source in enumerate(state.sources, start=1)
                    ]
                },
            )
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.REFRAG_CONTEXT,
                data={
                    "full_text_chunks": [
                        _stream_refrag_chunk(chunk, index)
                        for index, chunk in enumerate(state.refrag_context.full_text_chunks, start=1)
                    ],
                    "compressed_chunks": [
                        _stream_refrag_chunk(chunk, index)
                        for index, chunk in enumerate(
                            state.refrag_context.compressed_chunks,
                            start=len(state.refrag_context.full_text_chunks) + 1,
                        )
                    ],
                    "discarded_chunks": [
                        _stream_refrag_chunk(chunk, None) for chunk in state.refrag_context.discarded_chunks
                    ],
                    "total_original_tokens": state.refrag_context.total_original_tokens,
                    "total_context_tokens": state.refrag_context.total_context_tokens,
                    "compression_strategy": state.refrag_context.compression_strategy,
                },
            )
            await self._conversation_store.append_turn(
                user_id=dto.user_id,
                conversation_id=conversation_id,
                turn=ConversationTurnDTO(
                    query=query,
                    answer="".join(answer_parts),
                    sources=[
                        ConversationSourceDTO(
                            chunk_id=source.chunk_id,
                            document_id=source.document_id,
                            document_title=source.document_title,
                            page_number=source.page_number,
                            chunk_index=source.chunk_index,
                            score=source.score,
                        )
                        for source in state.sources
                    ],
                    created_at=datetime.now(UTC),
                ),
                ttl_seconds=settings.REDIS_CONVERSATION_TTL,
            )
            state.answer = "".join(answer_parts)
            state = await self._graph_runner.evaluate(state)
            latency_ms = int((perf_counter() - started_at) * 1000)
            await self._record_query(dto, query, state, latency_ms)
            if state.refrag_context is None:
                raise QueryProcessingException("query graph did not produce refrag_context")
            await self._record_chat_messages(
                conversation_id=conversation_id,
                query=query,
                answer=state.answer,
                sources=state.sources,
                refrag_context=_refrag_context_payload(state.refrag_context),
                eval_scores=state.eval_scores,
                trace_id=state.trace_id,
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

    async def _record_query(
        self,
        dto: QueryDTO,
        query: str,
        state: CortexQueryState,
        latency_ms: int,
    ) -> None:
        async with self._uow:
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
            await self._uow.commit()

    async def _ensure_chat_session(self, *, user_id: UUID, conversation_id: UUID, title: str) -> None:
        chat_repo = getattr(self._uow, "chat_repo", None)
        if chat_repo is None:
            return
        repository: IChatRepository = chat_repo
        async with self._uow:
            session = await repository.get_session(user_id=user_id, chat_id=conversation_id)
            if session is None:
                await repository.create_session(
                    user_id=user_id,
                    chat_id=conversation_id,
                    title=_title_from_query(title),
                )
                await self._uow.commit()

    async def _get_persisted_recent_turns(self, *, user_id: UUID, conversation_id: UUID) -> list[ConversationTurnDTO]:
        chat_repo = getattr(self._uow, "chat_repo", None)
        if chat_repo is None:
            return []
        repository: IChatRepository = chat_repo
        async with self._uow:
            return await repository.get_recent_turns(
                user_id=user_id,
                chat_id=conversation_id,
                limit=self.RECENT_TURN_LIMIT,
            )

    async def _record_chat_messages(
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
        chat_repo = getattr(self._uow, "chat_repo", None)
        if chat_repo is None:
            return
        repository: IChatRepository = chat_repo
        async with self._uow:
            await repository.append_message(chat_id=conversation_id, role="user", content=query)
            await repository.append_message(
                chat_id=conversation_id,
                role="assistant",
                content=answer,
                sources=[_source_payload(source) for source in sources],
                refrag_context=refrag_context,
                eval_scores=dict(eval_scores),
                trace_id=trace_id,
            )
            await self._uow.commit()


def _stream_refrag_chunk(chunk: RefragChunk, citation_index: int | None) -> dict[str, object]:
    return {
        "citation": f"[{citation_index}]" if citation_index is not None else None,
        "chunk_id": str(chunk.chunk_id),
        "document_id": str(chunk.document_id),
        "document_title": chunk.document_title,
        "representation": chunk.representation.value,
        "page_number": chunk.page_number,
        "chunk_index": chunk.chunk_index,
        "score": chunk.score,
        "context_text": chunk.context_text,
        "original_token_count": chunk.original_token_count,
        "context_token_count": chunk.context_token_count,
    }
