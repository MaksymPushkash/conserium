from uuid import UUID

from src.chats.repository import ChatRepository
from src.chats.schemas import (
    ChatDetailDTO,
    ChatDetailResponse,
    ChatListResponse,
    ChatMessageDTO,
    ChatMessageResponse,
    ChatSessionDTO,
    ChatSessionListDTO,
    ChatSessionResponse,
)
from src.kit.exceptions import ChatNotFoundException
from src.postgres import AsyncSession
from src.query.schemas import QuerySourceResponse, RefragContextResponse


class ChatService:
    async def create(self, session: AsyncSession, *, user_id: UUID, title: str | None) -> ChatSessionResponse:
        chat = await ChatRepository.from_session(session).create_session(
            user_id=user_id,
            title=_normalize_title(title),
        )
        await session.flush()
        return to_chat_session_response(chat)

    async def list(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> ChatListResponse:
        chats = await ChatRepository.from_session(session).list_sessions(user_id=user_id, limit=limit, offset=offset)
        return to_chat_list_response(chats)

    async def get(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        chat_id: UUID,
    ) -> ChatDetailResponse:
        detail = await ChatRepository.from_session(session).get_detail(
            user_id=user_id,
            chat_id=chat_id,
            message_limit=100,
        )
        if detail is None:
            raise ChatNotFoundException("Chat not found")
        return to_chat_detail_response(detail)

    async def rename(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        chat_id: UUID,
        title: str,
    ) -> ChatSessionResponse:
        chat = await ChatRepository.from_session(session).rename_session(
            user_id=user_id,
            chat_id=chat_id,
            title=_normalize_title(title),
        )
        await session.flush()
        if chat is None:
            raise ChatNotFoundException("Chat not found")
        return to_chat_session_response(chat)

    async def delete(self, session: AsyncSession, *, user_id: UUID, chat_id: UUID) -> None:
        await ChatRepository.from_session(session).delete_session(user_id=user_id, chat_id=chat_id)
        await session.flush()


def get_chat_service() -> ChatService:
    return chats


def to_chat_session_response(dto: ChatSessionDTO) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=dto.id,
        user_id=dto.user_id,
        title=dto.title,
        message_count=dto.message_count,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_chat_list_response(dto: ChatSessionListDTO) -> ChatListResponse:
    return ChatListResponse(
        items=[to_chat_session_response(item) for item in dto.items],
        total=dto.total,
        limit=dto.limit,
        offset=dto.offset,
    )


def to_chat_message_response(dto: ChatMessageDTO) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=dto.id,
        chat_id=dto.chat_id,
        role=dto.role,
        content=dto.content,
        sources=[QuerySourceResponse.model_validate(source) for source in dto.sources] if dto.sources else None,
        refrag_context=RefragContextResponse.model_validate(dto.refrag_context) if dto.refrag_context else None,
        eval_scores=dto.eval_scores,
        trace_id=dto.trace_id,
        created_at=dto.created_at,
    )


def to_chat_detail_response(dto: ChatDetailDTO) -> ChatDetailResponse:
    return ChatDetailResponse(
        session=to_chat_session_response(dto.session),
        messages=[to_chat_message_response(message) for message in dto.messages],
    )


def _normalize_title(title: str | None) -> str:
    normalized = (title or "").strip()
    if not normalized:
        return "New chat"
    return normalized[:120]


chats = ChatService()

__all__ = [
    "ChatService",
    "chats",
    "get_chat_service",
    "to_chat_detail_response",
    "to_chat_list_response",
    "to_chat_session_response",
]
