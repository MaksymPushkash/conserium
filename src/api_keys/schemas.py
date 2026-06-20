from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.kit.schemas import Schema


class CreateApiKeyRequest(Schema):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["ingest:write"], max_length=10)


class ApiKeyResponse(Schema):
    id: UUID
    name: str
    prefix: str
    scopes: list[str]
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class CreatedApiKeyResponse(Schema):
    api_key: ApiKeyResponse
    token: str


class ApiKeyListResponse(Schema):
    items: list[ApiKeyResponse]


__all__ = [
    "ApiKeyListResponse",
    "ApiKeyResponse",
    "CreateApiKeyRequest",
    "CreatedApiKeyResponse",
]
