from datetime import datetime

from pydantic import BaseModel, Field


class TopicResponse(BaseModel):
    name: str
    document_count: int
    last_document_at: datetime | None
    source_names: list[str] = Field(default_factory=list)
    pinned: bool = False
    ignored: bool = False


class TopicListResponse(BaseModel):
    items: list[TopicResponse]
    total: int
    limit: int
    offset: int


class TopicDocumentResponse(BaseModel):
    id: str
    title: str
    type: str
    status: str
    summary: str | None
    created_at: datetime


class TopicEventResponse(BaseModel):
    action: str
    topic_name: str
    display_name: str | None
    source_names: list[str] = Field(default_factory=list)
    created_at: datetime


class TopicDetailResponse(BaseModel):
    topic: TopicResponse
    documents: list[TopicDocumentResponse]
    events: list[TopicEventResponse] = Field(default_factory=list)


class TopicRenameRequest(BaseModel):
    display_name: str


class TopicMergeRequest(BaseModel):
    source_names: list[str]


class TopicPinRequest(BaseModel):
    pinned: bool = True


class TopicIgnoreRequest(BaseModel):
    ignored: bool = True
