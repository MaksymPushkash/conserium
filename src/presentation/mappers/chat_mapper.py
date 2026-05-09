from src.application.dtos.chat_dtos import ChatDetailDTO, ChatMessageDTO, ChatSessionDTO, ChatSessionListDTO
from src.presentation.schemas.chat import ChatDetailResponse, ChatListResponse, ChatMessageResponse, ChatSessionResponse


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
        sources=dto.sources,
        refrag_context=dto.refrag_context,
        eval_scores=dto.eval_scores,
        trace_id=dto.trace_id,
        created_at=dto.created_at,
    )


def to_chat_detail_response(dto: ChatDetailDTO) -> ChatDetailResponse:
    return ChatDetailResponse(
        session=to_chat_session_response(dto.session),
        messages=[to_chat_message_response(message) for message in dto.messages],
    )
