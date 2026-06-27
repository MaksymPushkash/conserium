from datetime import datetime

from src.kit.schemas import Schema


class TopicResponse(Schema):
    name: str
    document_count: int
    last_document_at: datetime | None
    source_names: list[str]
    pinned: bool = False
    ignored: bool = False


class TopicListResponse(Schema):
    items: list[TopicResponse]
    total: int
    limit: int
    offset: int


class TopicDocumentResponse(Schema):
    id: str
    title: str
    type: str
    status: str
    summary: str | None
    created_at: datetime


class TopicEventResponse(Schema):
    action: str
    topic_name: str
    display_name: str | None
    source_names: list[str]
    created_at: datetime


class TopicDetailResponse(Schema):
    topic: TopicResponse
    documents: list[TopicDocumentResponse]
    events: list[TopicEventResponse]


class TopicRenameRequest(Schema):
    display_name: str


class TopicMergeRequest(Schema):
    source_names: list[str]


class TopicPinRequest(Schema):
    pinned: bool = True


class TopicIgnoreRequest(Schema):
    ignored: bool = True


__all__ = [
    "TopicDetailResponse",
    "TopicDocumentResponse",
    "TopicEventResponse",
    "TopicIgnoreRequest",
    "TopicListResponse",
    "TopicMergeRequest",
    "TopicPinRequest",
    "TopicRenameRequest",
    "TopicResponse",
]
