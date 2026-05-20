from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.application.dtos.conversation_dtos import ConversationSourceDTO, ConversationTurnDTO
from src.application.use_cases.documents.base import ensure_collection_owner
from src.core.config import settings

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.dtos.query_dtos import QueryDTO, QuerySourceDTO
    from src.application.ports.conversations.conversation_store import IConversationStore
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class QueryConversationService:
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


def title_from_query(query: str) -> str:
    words = query.strip().split()
    title = " ".join(words[:8])
    return title[:120] or "New chat"
