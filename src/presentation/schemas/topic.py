from datetime import datetime

from pydantic import BaseModel


class TopicResponse(BaseModel):
    name: str
    document_count: int
    last_document_at: datetime | None


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


class TopicDetailResponse(BaseModel):
    topic: TopicResponse
    documents: list[TopicDocumentResponse]
