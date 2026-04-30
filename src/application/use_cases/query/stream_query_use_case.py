from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

from src.application.agents.query.state import CortexQueryState
from src.application.agents.query.streaming_graph_runner import StreamingQueryGraphRunner
from src.application.dtos.conversation_dtos import ConversationSourceDTO, ConversationTurnDTO
from src.application.dtos.query_dtos import QueryDTO
from src.application.dtos.query_stream_dtos import QueryStreamEventDTO, QueryStreamEventType
from src.application.dtos.refrag_dtos import RefragChunk
from src.application.ports.conversations.conversation_store import IConversationStore
from src.core.config import settings


class StreamQueryUseCase:
    RECENT_TURN_LIMIT = 6

    def __init__(self, graph_runner: StreamingQueryGraphRunner, conversation_store: IConversationStore) -> None:
        self._graph_runner = graph_runner
        self._conversation_store = conversation_store

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
        try:
            conversation_turns = await self._conversation_store.get_recent_turns(
                user_id=dto.user_id,
                conversation_id=conversation_id,
                limit=self.RECENT_TURN_LIMIT,
            )
            state = await self._graph_runner.prepare(
                CortexQueryState(
                    query=query,
                    user_id=dto.user_id,
                    limit=dto.limit,
                    conversation_id=conversation_id,
                    collection_id=dto.collection_id,
                    conversation_turns=conversation_turns,
                )
            )
            if state.refrag_context is None:
                raise ValueError("query graph did not produce refrag_context")

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
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.DONE,
                data={"query_id": str(query_id), "conversation_id": str(conversation_id)},
            )
        except Exception as exc:
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.ERROR,
                data={"query_id": str(query_id), "conversation_id": str(conversation_id), "message": str(exc)},
            )


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
