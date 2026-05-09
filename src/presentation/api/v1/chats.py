from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, Response, status

from src.application.use_cases.query.chat_use_cases import (
    CreateChatUseCase,
    DeleteChatUseCase,
    GetChatUseCase,
    ListChatsUseCase,
    RenameChatUseCase,
)
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.chat_mapper import (
    to_chat_detail_response,
    to_chat_list_response,
    to_chat_session_response,
)
from src.presentation.mappers.chat_request_mapper import (
    to_create_chat_dto,
    to_get_chat_dto,
    to_list_chats_dto,
    to_rename_chat_dto,
)
from src.presentation.schemas.chat import (
    ChatDetailResponse,
    ChatListResponse,
    ChatSessionResponse,
    CreateChatRequest,
    RenameChatRequest,
)

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_chat(
    body: CreateChatRequest,
    current_user: CurrentUser,
    use_case: FromDishka[CreateChatUseCase],
) -> ChatSessionResponse:
    result = await use_case(to_create_chat_dto(body, current_user.id))
    return to_chat_session_response(result)


@router.get("", response_model=ChatListResponse)
@inject
async def list_chats(
    current_user: CurrentUser,
    use_case: FromDishka[ListChatsUseCase],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ChatListResponse:
    result = await use_case(to_list_chats_dto(current_user.id, limit, offset))
    return to_chat_list_response(result)


@router.get("/{chat_id}", response_model=ChatDetailResponse)
@inject
async def get_chat(
    chat_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[GetChatUseCase],
) -> ChatDetailResponse:
    result = await use_case(to_get_chat_dto(chat_id, current_user.id))
    return to_chat_detail_response(result)


@router.patch("/{chat_id}", response_model=ChatSessionResponse)
@inject
async def rename_chat(
    chat_id: UUID,
    body: RenameChatRequest,
    current_user: CurrentUser,
    use_case: FromDishka[RenameChatUseCase],
) -> ChatSessionResponse:
    result = await use_case(to_rename_chat_dto(chat_id, body, current_user.id))
    return to_chat_session_response(result)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_chat(
    chat_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[DeleteChatUseCase],
) -> Response:
    await use_case(user_id=current_user.id, chat_id=chat_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
