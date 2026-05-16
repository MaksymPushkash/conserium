from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TopicDTO:
    name: str
    document_count: int
    last_document_at: datetime | None


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
class TopicDetailDTO:
    topic: TopicDTO
    documents: list[TopicDocumentDTO]
