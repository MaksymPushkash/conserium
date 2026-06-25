from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.query.schemas import QuerySourceResponse, RefragContextResponse

JsonObject = dict[str, object]


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


class ChatListResponse(BaseModel):
    items: list[ChatSessionResponse]
    total: int
    limit: int
    offset: int


class ChatMessageResponse(BaseModel):
    id: UUID
    chat_id: UUID
    role: str
    content: str
    sources: list[QuerySourceResponse] | None
    refrag_context: RefragContextResponse | None
    eval_scores: JsonObject | None
    trace_id: str | None
    created_at: datetime


class ChatDetailResponse(BaseModel):
    session: ChatSessionResponse
    messages: list[ChatMessageResponse]
