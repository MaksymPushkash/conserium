from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.application.dtos.conversation_dtos import ConversationSourceDTO, ConversationTurnDTO
from src.application.dtos.evaluation_dtos import QueryEvaluationRecordDTO
from src.application.dtos.query_dtos import QueryDebugDTO, QuerySourceDTO
from src.application.use_cases.documents.base import ensure_collection_owner
from src.core.config import settings

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from src.application.agents.query.state import CortexQueryState
    from src.application.dtos.query_dtos import QueryDTO
    from src.application.dtos.refrag_dtos import RefragChunk, RefragContextPackage
    from src.application.ports.conversations.conversation_store import IConversationStore
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class QueryOrchestrationService:
    RECENT_TURN_LIMIT = 6

    def __init__(self, conversation_store: IConversationStore, uow: IUnitOfWork) -> None:
        self._conversation_store = conversation_store
        self._uow = uow

    async def prepare_context(self, dto: QueryDTO, *, query: str, conversation_id: UUID) -> list[ConversationTurnDTO]:
        async with self._uow:
            await ensure_collection_owner(self._uow, dto.collection_id, dto.user_id)
        await self.ensure_chat_session(user_id=dto.user_id, conversation_id=conversation_id, title=query)
        conversation_turns = await self._conversation_store.get_recent_turns(
            user_id=dto.user_id,
            conversation_id=conversation_id,
            limit=self.RECENT_TURN_LIMIT,
        )
        if conversation_turns:
            return conversation_turns
        return await self.get_persisted_recent_turns(user_id=dto.user_id, conversation_id=conversation_id)

    async def append_turn(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        query: str,
        answer: str,
        sources: list[QuerySourceDTO],
    ) -> None:
        await self._conversation_store.append_turn(
            user_id=user_id,
            conversation_id=conversation_id,
            turn=ConversationTurnDTO(
                query=query,
                answer=answer,
                sources=[
                    ConversationSourceDTO(
                        chunk_id=source.chunk_id,
                        document_id=source.document_id,
                        document_title=source.document_title,
                        page_number=source.page_number,
                        chunk_index=source.chunk_index,
                        score=source.score,
                    )
                    for source in sources
                ],
                created_at=datetime.now(UTC),
            ),
            ttl_seconds=settings.REDIS_CONVERSATION_TTL,
        )

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
            await self._uow.commit()

    async def ensure_chat_session(self, *, user_id: UUID, conversation_id: UUID, title: str) -> None:
        async with self._uow:
            session = await self._uow.chat_repo.get_session(user_id=user_id, chat_id=conversation_id)
            if session is None:
                await self._uow.chat_repo.create_session(
                    user_id=user_id,
                    chat_id=conversation_id,
                    title=title_from_query(title),
                )
                await self._uow.commit()

    async def get_persisted_recent_turns(self, *, user_id: UUID, conversation_id: UUID) -> list[ConversationTurnDTO]:
        async with self._uow:
            return await self._uow.chat_repo.get_recent_turns(
                user_id=user_id,
                chat_id=conversation_id,
                limit=self.RECENT_TURN_LIMIT,
            )

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


def title_from_query(query: str) -> str:
    words = query.strip().split()
    title = " ".join(words[:8])
    return title[:120] or "New chat"


def source_payload(source: QuerySourceDTO) -> dict[str, object]:
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


def sources_payload(sources: list[QuerySourceDTO]) -> list[dict[str, object]]:
    return [source_payload(source) for source in sources]


def stream_metadata_payload(query_id: UUID, conversation_id: UUID, query: str, sources: list[QuerySourceDTO]) -> dict[str, object]:
    return {
        "query_id": str(query_id),
        "conversation_id": str(conversation_id),
        "query": query,
        "sources": [stream_source_payload(source, index, include_content=False) for index, source in enumerate(sources, start=1)],
    }


def stream_sources_payload(sources: list[QuerySourceDTO]) -> dict[str, object]:
    return {
        "sources": [stream_source_payload(source, index, include_content=True) for index, source in enumerate(sources, start=1)]
    }


def stream_source_payload(source: QuerySourceDTO, citation_index: int, *, include_content: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "citation": f"[{citation_index}]",
        "chunk_id": str(source.chunk_id),
        "document_id": str(source.document_id),
        "document_title": source.document_title,
        "page_number": source.page_number,
        "chunk_index": source.chunk_index,
        "score": source.score,
    }
    if include_content:
        payload["content"] = source.content
        payload["used_in_answer"] = source.used_in_answer
    return payload


def query_debug(original_query: str, state: CortexQueryState) -> QueryDebugDTO:
    return QueryDebugDTO(
        original_query=original_query,
        retrieval_query=state.retrieval_query or original_query,
        selected_collection_id=state.collection_id,
        selected_tags=list(state.tag_names or ()),
        promoted_document_ids=list(state.promoted_document_ids),
        retrieved_sources=list(state.retrieved_sources),
        final_sources=list(state.sources),
        used_sources=[source for source in state.sources if source.used_in_answer],
        filtered_sources=list(state.filtered_sources),
    )


def query_debug_payload(original_query: str, state: CortexQueryState) -> dict[str, object]:
    debug = query_debug(original_query, state)
    return {
        "original_query": debug.original_query,
        "retrieval_query": debug.retrieval_query,
        "selected_collection_id": str(debug.selected_collection_id) if debug.selected_collection_id else None,
        "selected_tags": debug.selected_tags,
        "promoted_document_ids": [str(document_id) for document_id in debug.promoted_document_ids],
        "retrieved_sources": sources_payload(debug.retrieved_sources),
        "final_sources": sources_payload(debug.final_sources),
        "used_sources": sources_payload(debug.used_sources),
        "filtered_sources": sources_payload(debug.filtered_sources),
    }


def refrag_context_payload(context: RefragContextPackage) -> dict[str, object]:
    return {
        "full_text_chunks": [refrag_chunk_payload(chunk) for chunk in context.full_text_chunks],
        "compressed_chunks": [refrag_chunk_payload(chunk) for chunk in context.compressed_chunks],
        "discarded_chunks": [refrag_chunk_payload(chunk) for chunk in context.discarded_chunks],
        "total_original_tokens": context.total_original_tokens,
        "total_context_tokens": context.total_context_tokens,
        "compression_strategy": context.compression_strategy,
    }


def stream_refrag_context_payload(context: RefragContextPackage) -> dict[str, object]:
    return {
        "full_text_chunks": [
            stream_refrag_chunk_payload(chunk, index) for index, chunk in enumerate(context.full_text_chunks, start=1)
        ],
        "compressed_chunks": [
            stream_refrag_chunk_payload(chunk, index)
            for index, chunk in enumerate(context.compressed_chunks, start=len(context.full_text_chunks) + 1)
        ],
        "discarded_chunks": [stream_refrag_chunk_payload(chunk, None) for chunk in context.discarded_chunks],
        "total_original_tokens": context.total_original_tokens,
        "total_context_tokens": context.total_context_tokens,
        "compression_strategy": context.compression_strategy,
    }


def refrag_chunk_payload(chunk: RefragChunk) -> dict[str, object]:
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


def stream_refrag_chunk_payload(chunk: RefragChunk, citation_index: int | None) -> dict[str, object]:
    payload = refrag_chunk_payload(chunk)
    payload["citation"] = f"[{citation_index}]" if citation_index is not None else None
    return payload


def mark_sources_used_in_answer(sources: list[QuerySourceDTO], answer: str) -> list[QuerySourceDTO]:
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
