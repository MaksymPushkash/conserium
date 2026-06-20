from dataclasses import dataclass
from datetime import datetime
from typing import final
from uuid import UUID

from pydantic import BaseModel, Field

from src.query.schemas import QuerySourceResponse, RefragContextResponse

JsonObject = dict[str, object]


@final
@dataclass(frozen=True, slots=True)
class ChatSessionDTO:
    id: UUID
    user_id: UUID
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime | None


@final
@dataclass(frozen=True, slots=True)
class ChatSessionListDTO:
    items: list[ChatSessionDTO]
    total: int
    limit: int
    offset: int


@final
@dataclass(frozen=True, slots=True)
class ChatMessageDTO:
    id: UUID
    chat_id: UUID
    role: str
    content: str
    sources: list[JsonObject] | None
    refrag_context: JsonObject | None
    eval_scores: JsonObject | None
    trace_id: str | None
    created_at: datetime


@final
@dataclass(frozen=True, slots=True)
class ChatDetailDTO:
    session: ChatSessionDTO
    messages: list[ChatMessageDTO]


@final
@dataclass(frozen=True, slots=True)
class CreateChatDTO:
    user_id: UUID
    title: str | None = None


@final
@dataclass(frozen=True, slots=True)
class RenameChatDTO:
    user_id: UUID
    chat_id: UUID
    title: str


@final
@dataclass(frozen=True, slots=True)
class GetChatDTO:
    user_id: UUID
    chat_id: UUID
    message_limit: int = 100


@final
@dataclass(frozen=True, slots=True)
class ListChatsDTO:
    user_id: UUID
    limit: int = 50
    offset: int = 0


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
