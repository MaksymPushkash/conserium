from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.application.dtos.query_dtos import QuerySourceDTO


@dataclass(frozen=True, slots=True)
class DraftRecord:
    id: UUID
    user_id: UUID
    collection_id: UUID | None
    title: str
    prompt: str
    template_id: str
    scope_type: str
    topic: str | None
    knowledge_gap_id: str | None
    scope_metadata: dict[str, object]
    markdown: str
    sources: list[QuerySourceDTO]
    gaps: list[str]
    current_version_id: UUID
    version_number: int
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class DraftVersionRecord:
    id: UUID
    draft_id: UUID
    user_id: UUID
    version_number: int
    title: str
    prompt: str
    template_id: str
    scope_type: str
    collection_id: UUID | None
    topic: str | None
    knowledge_gap_id: str | None
    scope_metadata: dict[str, object]
    markdown: str
    sources: list[QuerySourceDTO]
    gaps: list[str]
    created_at: datetime | None


class IDraftRepository(ABC):
    @abstractmethod
    async def create_with_version(self, *, draft: DraftRecord, version: DraftVersionRecord) -> DraftRecord: ...

    @abstractmethod
    async def append_version(self, *, draft_id: UUID, version: DraftVersionRecord) -> DraftRecord: ...

    @abstractmethod
    async def get_by_id(self, draft_id: UUID) -> DraftRecord | None: ...

    @abstractmethod
    async def list_by_user_id(
        self,
        *,
        user_id: UUID,
        collection_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[DraftRecord]: ...

    @abstractmethod
    async def list_versions(self, *, draft_id: UUID, user_id: UUID) -> list[DraftVersionRecord]: ...

    @abstractmethod
    async def get_version(self, *, draft_id: UUID, version_id: UUID, user_id: UUID) -> DraftVersionRecord | None: ...

    @abstractmethod
    async def restore_version(self, *, version: DraftVersionRecord) -> DraftRecord: ...

    @abstractmethod
    async def delete(self, draft_id: UUID) -> None: ...
