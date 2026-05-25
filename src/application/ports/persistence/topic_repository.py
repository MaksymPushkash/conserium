from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TopicRecord:
    name: str
    document_count: int
    last_document_at: datetime | None
    source_names: tuple[str, ...] = ()
    pinned: bool = False
    ignored: bool = False


@dataclass(frozen=True, slots=True)
class TopicOverrideRecord:
    source_name: str
    display_name: str
    pinned: bool
    ignored: bool


@dataclass(frozen=True, slots=True)
class TopicOverrideEventRecord:
    action: str
    topic_name: str
    display_name: str | None
    source_names: tuple[str, ...]
    created_at: datetime


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

    @abstractmethod
    async def get_details_by_names(
        self,
        user_id: UUID,
        *,
        names: set[str],
        document_limit: int,
    ) -> dict[str, TopicDetailRecord]: ...

    @abstractmethod
    async def list_overrides(self, user_id: UUID) -> list[TopicOverrideRecord]: ...

    @abstractmethod
    async def rename_topic(self, *, user_id: UUID, source_name: str, display_name: str) -> TopicRecord: ...

    @abstractmethod
    async def merge_topics(self, *, user_id: UUID, source_names: list[str], display_name: str) -> TopicRecord: ...

    @abstractmethod
    async def set_pinned(self, *, user_id: UUID, name: str, pinned: bool) -> TopicRecord: ...

    @abstractmethod
    async def set_ignored(self, *, user_id: UUID, name: str, ignored: bool) -> TopicRecord: ...

    @abstractmethod
    async def list_override_events(self, *, user_id: UUID, topic_name: str, limit: int) -> list[TopicOverrideEventRecord]: ...
