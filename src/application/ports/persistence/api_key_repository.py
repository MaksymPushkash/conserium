from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ApiKeyRecord:
    id: UUID
    user_id: UUID
    name: str
    key_hash: str
    prefix: str
    scopes: list[str]
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class IApiKeyRepository(ABC):
    @abstractmethod
    async def create(self, record: ApiKeyRecord) -> ApiKeyRecord: ...

    @abstractmethod
    async def list_by_user_id(self, user_id: UUID) -> list[ApiKeyRecord]: ...

    @abstractmethod
    async def get_by_hash(self, key_hash: str) -> ApiKeyRecord | None: ...

    @abstractmethod
    async def mark_used(self, api_key_id: UUID, used_at: datetime) -> None: ...

    @abstractmethod
    async def revoke(self, *, api_key_id: UUID, user_id: UUID, revoked_at: datetime) -> None: ...
