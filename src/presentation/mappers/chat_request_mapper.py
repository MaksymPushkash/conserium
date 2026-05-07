from uuid import UUID

from src.application.dtos.chat_dtos import CreateChatDTO, GetChatDTO, ListChatsDTO, RenameChatDTO
from src.presentation.schemas.chat import CreateChatRequest, RenameChatRequest


def to_create_chat_dto(body: CreateChatRequest, user_id: UUID) -> CreateChatDTO:
    return CreateChatDTO(user_id=user_id, title=body.title)


def to_list_chats_dto(user_id: UUID, limit: int, offset: int) -> ListChatsDTO:
    return ListChatsDTO(user_id=user_id, limit=limit, offset=offset)


def to_get_chat_dto(chat_id: UUID, user_id: UUID) -> GetChatDTO:
    return GetChatDTO(user_id=user_id, chat_id=chat_id)


def to_rename_chat_dto(chat_id: UUID, body: RenameChatRequest, user_id: UUID) -> RenameChatDTO:
    return RenameChatDTO(user_id=user_id, chat_id=chat_id, title=body.title)
