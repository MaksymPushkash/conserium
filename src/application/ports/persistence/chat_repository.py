from abc import ABC, abstractmethod
from uuid import UUID

from src.application.dtos.chat_dtos import ChatDetailDTO, ChatMessageDTO, ChatSessionDTO, ChatSessionListDTO, JsonObject
from src.application.dtos.conversation_dtos import ConversationTurnDTO


class IChatRepository(ABC):
    @abstractmethod
    async def create_session(
        self,
        *,
        user_id: UUID,
        title: str,
        chat_id: UUID | None = None,
    ) -> ChatSessionDTO: ...

    @abstractmethod
    async def get_session(self, *, user_id: UUID, chat_id: UUID) -> ChatSessionDTO | None: ...

    @abstractmethod
    async def list_sessions(self, *, user_id: UUID, limit: int, offset: int) -> ChatSessionListDTO: ...

    @abstractmethod
    async def get_detail(self, *, user_id: UUID, chat_id: UUID, message_limit: int) -> ChatDetailDTO | None: ...

    @abstractmethod
    async def rename_session(self, *, user_id: UUID, chat_id: UUID, title: str) -> ChatSessionDTO | None: ...

    @abstractmethod
    async def delete_session(self, *, user_id: UUID, chat_id: UUID) -> None: ...

    @abstractmethod
    async def append_message(
        self,
        *,
        chat_id: UUID,
        role: str,
        content: str,
        sources: list[JsonObject] | None = None,
        refrag_context: JsonObject | None = None,
        eval_scores: JsonObject | None = None,
        trace_id: str | None = None,
    ) -> ChatMessageDTO: ...

    @abstractmethod
    async def get_recent_turns(self, *, user_id: UUID, chat_id: UUID, limit: int) -> list[ConversationTurnDTO]: ...
