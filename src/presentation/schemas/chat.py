from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.application.dtos.chat_dtos import ChatDetailDTO, ChatMessageDTO, ChatSessionDTO, ChatSessionListDTO, JsonObject


class CreateChatRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class RenameChatRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ChatSessionResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_dto(cls, dto: ChatSessionDTO) -> "ChatSessionResponse":
        return cls(
            id=dto.id,
            user_id=dto.user_id,
            title=dto.title,
            message_count=dto.message_count,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


class ChatListResponse(BaseModel):
    items: list[ChatSessionResponse]
    total: int
    limit: int
    offset: int

    @classmethod
    def from_dto(cls, dto: ChatSessionListDTO) -> "ChatListResponse":
        return cls(
            items=[ChatSessionResponse.from_dto(item) for item in dto.items],
            total=dto.total,
            limit=dto.limit,
            offset=dto.offset,
        )


class ChatMessageResponse(BaseModel):
    id: UUID
    chat_id: UUID
    role: str
    content: str
    sources: list[JsonObject] | None
    refrag_context: JsonObject | None
    eval_scores: JsonObject | None
    trace_id: str | None
    created_at: datetime

    @classmethod
    def from_dto(cls, dto: ChatMessageDTO) -> "ChatMessageResponse":
        return cls(
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


class ChatDetailResponse(BaseModel):
    session: ChatSessionResponse
    messages: list[ChatMessageResponse]

    @classmethod
    def from_dto(cls, dto: ChatDetailDTO) -> "ChatDetailResponse":
        return cls(
            session=ChatSessionResponse.from_dto(dto.session),
            messages=[ChatMessageResponse.from_dto(message) for message in dto.messages],
        )
