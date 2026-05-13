from __future__ import annotations

import re
from datetime import UTC, datetime
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog

from src.application.agents.query.state import CortexQueryState
from src.application.dtos.conversation_dtos import ConversationSourceDTO, ConversationTurnDTO
from src.application.dtos.evaluation_dtos import QueryEvaluationRecordDTO
from src.application.dtos.query_dtos import QueryResultDTO, QuerySourceDTO
from src.application.use_cases.documents.base import ensure_collection_owner
from src.core.config import settings
from src.domain.exceptions import QueryProcessingException, QueryValidationException

if TYPE_CHECKING:
    from collections.abc import Mapping

    from src.application.agents.query.graph_runner import QueryGraphRunner
    from src.application.dtos.query_dtos import QueryDTO
    from src.application.dtos.refrag_dtos import RefragChunk, RefragContextPackage
    from src.application.ports.conversations.conversation_store import IConversationStore
    from src.application.ports.persistence.chat_repository import IChatRepository
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
        self._conversation_store = conversation_store
        self._uow = uow

    async def __call__(self, dto: QueryDTO) -> QueryResultDTO:
        query = dto.query.strip()
        if not query:
            raise QueryValidationException("query cannot be empty")
        async with self._uow:
            await ensure_collection_owner(self._uow, dto.collection_id, dto.user_id)

        conversation_id = dto.conversation_id or uuid4()
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
        started_at = perf_counter()
        state = await self._graph_runner.run(
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
        latency_ms = int((perf_counter() - started_at) * 1000)
        if state.refrag_context is None:
            raise QueryProcessingException("query graph did not produce refrag_context")
        state.sources = _mark_sources_used_in_answer(state.sources, state.answer)
        await self._conversation_store.append_turn(
            user_id=dto.user_id,
            conversation_id=conversation_id,
            turn=ConversationTurnDTO(
                query=query,
                answer=state.answer,
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
        await self._record_query(dto, query, state, latency_ms)
        await self._record_chat_messages(
            conversation_id=conversation_id,
            query=query,
            result=QueryResultDTO(
                conversation_id=conversation_id,
                query=query,
                answer=state.answer,
                sources=state.sources,
                refrag_context=state.refrag_context,
            ),
            eval_scores=state.eval_scores,
            trace_id=state.trace_id,
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
        repository = chat_repo
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
        result: QueryResultDTO,
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
                content=result.answer,
                sources=[_source_payload(source) for source in result.sources],
                refrag_context=_refrag_context_payload(result.refrag_context),
                eval_scores=dict(eval_scores),
                trace_id=trace_id,
            )
            await self._uow.commit()


def _title_from_query(query: str) -> str:
    words = query.strip().split()
    title = " ".join(words[:8])
    return title[:120] or "New chat"


def _source_payload(source: QuerySourceDTO) -> dict[str, object]:
    return {
        "chunk_id": str(source.chunk_id),
        "document_id": str(source.document_id),
        "document_title": source.document_title,
        "content": source.content,
        "page_number": source.page_number,
        "chunk_index": source.chunk_index,
        "score": source.score,
        "used_in_answer": source.used_in_answer,
    }


def _refrag_context_payload(context: RefragContextPackage) -> dict[str, object]:
    return {
        "full_text_chunks": [_refrag_chunk_payload(chunk) for chunk in context.full_text_chunks],
        "compressed_chunks": [_refrag_chunk_payload(chunk) for chunk in context.compressed_chunks],
        "discarded_chunks": [_refrag_chunk_payload(chunk) for chunk in context.discarded_chunks],
        "total_original_tokens": context.total_original_tokens,
        "total_context_tokens": context.total_context_tokens,
        "compression_strategy": context.compression_strategy,
    }


def _refrag_chunk_payload(chunk: RefragChunk) -> dict[str, object]:
    return {
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


def _mark_sources_used_in_answer(sources: list[QuerySourceDTO], answer: str) -> list[QuerySourceDTO]:
    used_citations = {int(match) for match in re.findall(r"\[(\d+)\]", answer)}
    return [
        QuerySourceDTO(
            chunk_id=source.chunk_id,
            document_id=source.document_id,
            document_title=source.document_title,
            content=source.content,
            page_number=source.page_number,
            chunk_index=source.chunk_index,
            score=source.score,
            used_in_answer=index in used_citations,
        )
        for index, source in enumerate(sources, start=1)
    ]
