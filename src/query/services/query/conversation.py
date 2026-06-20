from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.kit.exceptions import ResourceNotFoundException
from src.query.schemas import ConversationSourceDTO, ConversationTurnDTO
from src.settings import settings

if TYPE_CHECKING:
    from uuid import UUID

    from src.chats.repository import ChatRepository
    from src.collections.repository import CollectionRepository
    from src.kit.ports.conversations.conversation_store import IConversationStore
    from src.postgres import AsyncSession
    from src.query.schemas import QueryDTO, QuerySourceDTO


class QueryConversationService:
    RECENT_TURN_LIMIT = 6

    def __init__(
        self,
        conversation_store: IConversationStore,
        session: AsyncSession,
        chat_repo: ChatRepository,
        collection_repo: CollectionRepository,
    ) -> None:
        self._conversation_store = conversation_store
        self._session = session
        self._chat_repo = chat_repo
        self._collection_repo = collection_repo

    async def prepare_context(self, dto: QueryDTO, *, query: str, conversation_id: UUID) -> list[ConversationTurnDTO]:
        if dto.collection_id is not None:
            collection = await self._collection_repo.get_by_id(dto.collection_id)
            if collection is None or collection.user_id != dto.user_id:
                raise ResourceNotFoundException("collection not found")
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
        session = await self._chat_repo.get_session(user_id=user_id, chat_id=conversation_id)
        if session is None:
            await self._chat_repo.create_session(
                user_id=user_id,
                chat_id=conversation_id,
                title=title_from_query(title),
            )
            await self._session.flush()

    async def get_persisted_recent_turns(self, *, user_id: UUID, conversation_id: UUID) -> list[ConversationTurnDTO]:
        return await self._chat_repo.get_recent_turns(
            user_id=user_id,
            chat_id=conversation_id,
            limit=self.RECENT_TURN_LIMIT,
        )


def title_from_query(query: str) -> str:
    words = query.strip().split()
    title = " ".join(words[:8])
    return title[:120] or "New chat"
