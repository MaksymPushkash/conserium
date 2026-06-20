from abc import ABC, abstractmethod
from uuid import UUID

from src.query.schemas import ConversationTurnDTO


class IConversationStore(ABC):
    @abstractmethod
    async def get_recent_turns(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        limit: int,
    ) -> list[ConversationTurnDTO]: ...

    @abstractmethod
    async def append_turn(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        turn: ConversationTurnDTO,
        ttl_seconds: int,
    ) -> None: ...
