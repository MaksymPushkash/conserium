from datetime import UTC, datetime
from uuid import uuid4

from src.application.agents.query.graph_runner import QueryGraphRunner
from src.application.agents.query.state import CortexQueryState
from src.application.dtos.conversation_dtos import ConversationSourceDTO, ConversationTurnDTO
from src.application.dtos.query_dtos import QueryDTO, QueryResultDTO
from src.application.ports.conversations.conversation_store import IConversationStore
from src.core.config import settings


class QueryUseCase:
    RECENT_TURN_LIMIT = 6

    def __init__(self, graph_runner: QueryGraphRunner, conversation_store: IConversationStore) -> None:
        self._graph_runner = graph_runner
        self._conversation_store = conversation_store

    async def __call__(self, dto: QueryDTO) -> QueryResultDTO:
        query = dto.query.strip()
        if not query:
            raise ValueError("query cannot be empty")

        conversation_id = dto.conversation_id or uuid4()
        conversation_turns = await self._conversation_store.get_recent_turns(
            user_id=dto.user_id,
            conversation_id=conversation_id,
            limit=self.RECENT_TURN_LIMIT,
        )
        state = await self._graph_runner.run(
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
        return QueryResultDTO(
            conversation_id=conversation_id,
            query=query,
            answer=state.answer,
            sources=state.sources,
            refrag_context=state.refrag_context,
        )
