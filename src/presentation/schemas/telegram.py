from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.presentation.schemas.external_intake import ExternalIngestRequest, ExternalIngestResponse


class TelegramPairingCodeResponse(BaseModel):
    id: UUID
    code: str
    expires_at: datetime


class TelegramChatBindingResponse(BaseModel):
    id: UUID
    chat_id: str
    chat_username: str | None
    chat_title: str | None
    paired_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class TelegramStatusResponse(BaseModel):
    bindings: list[TelegramChatBindingResponse]


class TelegramConsumePairingRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    chat_id: str = Field(min_length=1, max_length=64)
    chat_username: str | None = Field(default=None, max_length=255)
    chat_title: str | None = Field(default=None, max_length=255)


class TelegramIngestRequest(ExternalIngestRequest):
    chat_id: str = Field(min_length=1, max_length=64)


class TelegramIngestResponse(ExternalIngestResponse): ...
