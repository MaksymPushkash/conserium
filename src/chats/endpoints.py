from uuid import UUID

from fastapi import Depends, Query, Response, status

from src.auth.auth import CurrentUser
from src.chats.schemas import (
    ChatDetailResponse,
    ChatListResponse,
    ChatSessionResponse,
    CreateChatRequest,
    RenameChatRequest,
)
from src.chats.service import ChatService, get_chat_service
from src.postgres import AsyncReadSession, AsyncSession, get_db_read_session, get_db_session
from src.routing import APIRouter

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    body: CreateChatRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: ChatService = Depends(get_chat_service),
) -> ChatSessionResponse:
    return await service.create(session, user_id=current_user.id, title=body.title)


@router.get("", response_model=ChatListResponse)
async def list_chats(
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: ChatService = Depends(get_chat_service),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ChatListResponse:
    return await service.list(session, user_id=current_user.id, limit=limit, offset=offset)


@router.get("/{chat_id}", response_model=ChatDetailResponse)
async def get_chat(
    chat_id: UUID,
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: ChatService = Depends(get_chat_service),
) -> ChatDetailResponse:
    return await service.get(session, user_id=current_user.id, chat_id=chat_id)


@router.patch("/{chat_id}", response_model=ChatSessionResponse)
async def rename_chat(
    chat_id: UUID,
    body: RenameChatRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: ChatService = Depends(get_chat_service),
) -> ChatSessionResponse:
    return await service.rename(session, user_id=current_user.id, chat_id=chat_id, title=body.title)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: ChatService = Depends(get_chat_service),
) -> Response:
    await service.delete(session, user_id=current_user.id, chat_id=chat_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
