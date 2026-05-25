from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class CollectionResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    color: str | None
    created_at: datetime
    updated_at: datetime | None


class CollectionListResponse(BaseModel):
    items: list[CollectionResponse]
    total: int
    limit: int
    offset: int


class CollectionWorkspaceStatsResponse(BaseModel):
    total_documents: int
    ready_documents: int
    processing_documents: int
    failed_documents: int
    topic_count: int
    recent_question_count: int


class CollectionWorkspaceDocumentResponse(BaseModel):
    id: UUID
    title: str
    type: str
    status: str
    summary: str | None
    tags: list[str]
    activity_temperature: str
    created_at: datetime
    updated_at: datetime | None


class CollectionWorkspaceTopicResponse(BaseModel):
    name: str
    document_count: int
    last_document_at: datetime | None


class CollectionWorkspaceGapResponse(BaseModel):
    title: str
    reason: str
    severity: str
    id: str | None = None
    topic: str | None = None
    coverage_ratio: float | None = None
    missing_source_types: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)


class CollectionWorkspaceQuestionResponse(BaseModel):
    query_text: str
    answer_preview: str | None
    result_count: int
    created_at: datetime


class CollectionWorkspaceDraftResponse(BaseModel):
    id: UUID
    title: str
    prompt: str
    template_id: str
    scope_type: str
    topic: str | None
    knowledge_gap_id: str | None
    version_number: int
    created_at: datetime
    updated_at: datetime | None


class CollectionWorkspaceComparisonResponse(BaseModel):
    id: UUID
    left_title: str
    right_title: str
    summary: str
    dimensions: list[str]
    created_at: datetime | None


class CollectionWorkspaceResponse(BaseModel):
    collection: CollectionResponse
    stats: CollectionWorkspaceStatsResponse
    documents: list[CollectionWorkspaceDocumentResponse]
    topics: list[CollectionWorkspaceTopicResponse]
    gaps: list[CollectionWorkspaceGapResponse]
    recent_questions: list[CollectionWorkspaceQuestionResponse]
    recent_drafts: list[CollectionWorkspaceDraftResponse] = Field(default_factory=list)
    recent_comparisons: list[CollectionWorkspaceComparisonResponse] = Field(default_factory=list)
