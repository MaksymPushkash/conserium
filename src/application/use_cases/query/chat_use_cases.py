from uuid import UUID

from src.application.dtos.chat_dtos import (
    ChatDetailDTO,
    ChatSessionDTO,
    ChatSessionListDTO,
    CreateChatDTO,
    GetChatDTO,
    ListChatsDTO,
    RenameChatDTO,
)
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.domain.exceptions import ChatNotFoundException


class CreateChatUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: CreateChatDTO) -> ChatSessionDTO:
        title = _normalize_title(dto.title)
        async with self._uow:
            session = await self._uow.chat_repo.create_session(user_id=dto.user_id, title=title)
            await self._uow.commit()
            return session


class ListChatsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: ListChatsDTO) -> ChatSessionListDTO:
        async with self._uow:
            return await self._uow.chat_repo.list_sessions(user_id=dto.user_id, limit=dto.limit, offset=dto.offset)


class GetChatUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: GetChatDTO) -> ChatDetailDTO:
        async with self._uow:
            detail = await self._uow.chat_repo.get_detail(
                user_id=dto.user_id,
                chat_id=dto.chat_id,
                message_limit=dto.message_limit,
            )
        if detail is None:
            raise ChatNotFoundException("Chat not found")
        return detail


class RenameChatUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: RenameChatDTO) -> ChatSessionDTO:
        async with self._uow:
            session = await self._uow.chat_repo.rename_session(
                user_id=dto.user_id,
                chat_id=dto.chat_id,
                title=_normalize_title(dto.title),
            )
            await self._uow.commit()
        if session is None:
            raise ChatNotFoundException("Chat not found")
        return session


class DeleteChatUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, chat_id: UUID) -> None:
        async with self._uow:
            await self._uow.chat_repo.delete_session(user_id=user_id, chat_id=chat_id)
            await self._uow.commit()


def _normalize_title(title: str | None) -> str:
    normalized = (title or "").strip()
    if not normalized:
        return "New chat"
    return normalized[:120]
