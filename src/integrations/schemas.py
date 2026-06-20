from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime  # noqa: TC003
from typing import Any, final
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, Field

from src.webhooks.schemas import ExternalIngestRequest, ExternalIngestResponse


@dataclass(frozen=True, slots=True)
class ApiKeyDTO:
    id: UUID
    user_id: UUID
    name: str
    prefix: str
    scopes: list[str]
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CreatedApiKeyDTO:
    api_key: ApiKeyDTO
    token: str


@dataclass(frozen=True, slots=True)
class CreateApiKeyDTO:
    user_id: UUID
    name: str
    scopes: list[str]


@dataclass(frozen=True, slots=True)
class ApiKeyPrincipalDTO:
    user_id: UUID
    api_key_id: UUID
    scopes: list[str]


@final
@dataclass(frozen=True, slots=True)
class ExternalConnectionDTO:
    id: UUID
    user_id: UUID
    provider: str
    workspace_id: str | None
    workspace_name: str | None
    access_token_encrypted: str
    bot_id: str | None
    owner: dict[str, Any] | None
    default_parent_page_id: str | None
    default_parent_page_title: str | None


@dataclass(frozen=True, slots=True)
class NotionPageContentDTO:
    id: str
    title: str
    markdown: str


@dataclass(frozen=True, slots=True)
class TelegramChatBindingDTO:
    id: UUID
    user_id: UUID
    api_key_id: UUID | None
    chat_id: str
    chat_username: str | None
    chat_title: str | None
    paired_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class TelegramStatusDTO:
    bindings: list[TelegramChatBindingDTO]


@dataclass(frozen=True, slots=True)
class FetchedWebResource:
    title: str | None
    excerpt: str | None


@dataclass(frozen=True, slots=True)
class NotionOAuthToken:
    access_token: str
    workspace_id: str | None
    workspace_name: str | None
    bot_id: str | None
    owner: dict[str, Any] | None


class NotionConnectionResponse(BaseModel):
    connected: bool
    workspace_id: str | None
    workspace_name: str | None
    bot_id: str | None
    default_parent_page_id: str | None
    default_parent_page_title: str | None


class IntegrationConnectUrlResponse(BaseModel):
    url: str


class NotionConnectionSettingsRequest(BaseModel):
    default_parent_page_id: str | None = None
    default_parent_page_title: str | None = None


class NotionPageResponse(BaseModel):
    id: str
    title: str


class NotionImportRequest(BaseModel):
    page_id: str = Field(min_length=1, max_length=120)
    collection_id: UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)


class NotionImportResponse(ExternalIngestResponse): ...


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
