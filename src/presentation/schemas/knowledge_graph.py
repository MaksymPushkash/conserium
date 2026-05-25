from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeGraphNodeResponse(BaseModel):
    id: str
    kind: str
    label: str
    detail: str | None = None
    collection_id: UUID | None = None
    summary: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    suggested_questions: list[str] | None = None
    source_names: list[str] = Field(default_factory=list)
    is_pinned: bool = False
    is_ignored: bool = False


class KnowledgeGraphEdgeResponse(BaseModel):
    id: str
    source_id: str
    target_id: str
    relation_type: str
    label: str
    score: float


class KnowledgeGraphResponse(BaseModel):
    nodes: list[KnowledgeGraphNodeResponse]
    edges: list[KnowledgeGraphEdgeResponse]


class KnowledgeGraphInsightResponse(BaseModel):
    kind: str
    title: str
    description: str
    severity: str
    count: int
    nodes: list[KnowledgeGraphNodeResponse] = Field(default_factory=list)


class KnowledgeGraphInsightsResponse(BaseModel):
    items: list[KnowledgeGraphInsightResponse]


class KnowledgeGraphConcernCreateRequest(BaseModel):
    message: str
    node_id: str | None = None
    node_kind: str | None = None
    node_label: str | None = None


class KnowledgeGraphConcernResponse(BaseModel):
    id: UUID
    node_id: str | None
    node_kind: str | None
    node_label: str | None
    message: str
    status: str
    created_at: datetime
