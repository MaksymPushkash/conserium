from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["ingest:write"], max_length=10)


class ApiKeyResponse(BaseModel):
    id: UUID
    name: str
    prefix: str
    scopes: list[str]
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class CreatedApiKeyResponse(BaseModel):
    api_key: ApiKeyResponse
    token: str


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyResponse]
