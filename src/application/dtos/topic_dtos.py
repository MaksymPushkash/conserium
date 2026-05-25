from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TopicDTO:
    name: str
    document_count: int
    last_document_at: datetime | None
    source_names: tuple[str, ...] = ()
    pinned: bool = False
    ignored: bool = False


@dataclass(frozen=True, slots=True)
class TopicListDTO:
    items: list[TopicDTO]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class TopicDocumentDTO:
    id: str
    title: str
    type: str
    status: str
    summary: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TopicEventDTO:
    action: str
    topic_name: str
    display_name: str | None
    source_names: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TopicDetailDTO:
    topic: TopicDTO
    documents: list[TopicDocumentDTO]
    events: tuple[TopicEventDTO, ...] = ()
