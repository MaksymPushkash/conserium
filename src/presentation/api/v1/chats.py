from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, Response, status

from src.application.dtos.chat_dtos import CreateChatDTO, GetChatDTO, ListChatsDTO, RenameChatDTO
from src.application.use_cases.query.chat_use_cases import (
    CreateChatUseCase,
    DeleteChatUseCase,
    GetChatUseCase,
    ListChatsUseCase,
    RenameChatUseCase,
)
from src.presentation.dependencies.auth import CurrentUser
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
    result = await use_case(CreateChatDTO(user_id=current_user.id, title=body.title))
    return ChatSessionResponse.from_dto(result)


@router.get("", response_model=ChatListResponse)
@inject
async def list_chats(
    current_user: CurrentUser,
    use_case: FromDishka[ListChatsUseCase],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ChatListResponse:
    result = await use_case(ListChatsDTO(user_id=current_user.id, limit=limit, offset=offset))
    return ChatListResponse.from_dto(result)


@router.get("/{chat_id}", response_model=ChatDetailResponse)
@inject
async def get_chat(
    chat_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[GetChatUseCase],
) -> ChatDetailResponse:
    result = await use_case(GetChatDTO(user_id=current_user.id, chat_id=chat_id))
    return ChatDetailResponse.from_dto(result)


@router.patch("/{chat_id}", response_model=ChatSessionResponse)
@inject
async def rename_chat(
    chat_id: UUID,
    body: RenameChatRequest,
    current_user: CurrentUser,
    use_case: FromDishka[RenameChatUseCase],
) -> ChatSessionResponse:
    result = await use_case(RenameChatDTO(user_id=current_user.id, chat_id=chat_id, title=body.title))
    return ChatSessionResponse.from_dto(result)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_chat(
    chat_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[DeleteChatUseCase],
) -> Response:
    await use_case(user_id=current_user.id, chat_id=chat_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
