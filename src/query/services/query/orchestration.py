from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from src.query.agents.state import ConseriumQueryState
    from src.query.schemas import ConversationTurn, QueryPayload, QuerySource
    from src.query.services.query.conversation import QueryConversationService
    from src.query.services.query.persistence import QueryPersistenceService


class QueryOrchestrationService:
    def __init__(self, conversation: QueryConversationService, persistence: QueryPersistenceService) -> None:
        self._conversation = conversation
        self._persistence = persistence

    async def prepare_context(self, dto: QueryPayload, *, query: str, conversation_id: UUID) -> list[ConversationTurn]:
        return await self._conversation.prepare_context(dto, query=query, conversation_id=conversation_id)

    async def append_turn(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        query: str,
        answer: str,
        sources: list[QuerySource],
    ) -> None:
        await self._conversation.append_turn(
            user_id=user_id,
            conversation_id=conversation_id,
            query=query,
            answer=answer,
            sources=sources,
        )

    async def record_query(self, dto: QueryPayload, query: str, state: ConseriumQueryState, latency_ms: int) -> None:
        await self._persistence.record_query(dto, query, state, latency_ms)

    async def record_interaction(
        self,
        dto: QueryPayload,
        *,
        query: str,
        state: ConseriumQueryState,
        latency_ms: int,
        refrag_context: dict[str, object],
        conversation_id: UUID,
    ) -> None:
        await self._persistence.record_interaction(
            dto,
            query=query,
            state=state,
            latency_ms=latency_ms,
            refrag_context=refrag_context,
            conversation_id=conversation_id,
        )

    async def ensure_chat_session(self, *, user_id: UUID, conversation_id: UUID, title: str) -> None:
        await self._conversation.ensure_chat_session(user_id=user_id, conversation_id=conversation_id, title=title)

    async def get_persisted_recent_turns(self, *, user_id: UUID, conversation_id: UUID) -> list[ConversationTurn]:
        return await self._conversation.get_persisted_recent_turns(user_id=user_id, conversation_id=conversation_id)
