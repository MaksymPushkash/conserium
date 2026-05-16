from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TopicRecord:
    name: str
    document_count: int
    last_document_at: datetime | None


@dataclass(frozen=True, slots=True)
class TopicDocumentRecord:
    id: UUID
    title: str
    type: str
    status: str
    summary: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TopicDetailRecord:
    topic: TopicRecord
    documents: list[TopicDocumentRecord]


class ITopicRepository(ABC):
    @abstractmethod
    async def list_by_user_id(self, user_id: UUID, *, limit: int, offset: int) -> list[TopicRecord]: ...

    @abstractmethod
    async def count_by_user_id(self, user_id: UUID) -> int: ...

    @abstractmethod
    async def get_detail_by_name(
        self,
        user_id: UUID,
        *,
        name: str,
        document_limit: int,
    ) -> TopicDetailRecord | None: ...
