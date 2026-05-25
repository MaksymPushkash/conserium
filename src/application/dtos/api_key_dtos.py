from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


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
