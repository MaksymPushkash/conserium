from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class KnowledgeGraphNodeResponse(BaseModel):
    id: str
    kind: str
    label: str
    detail: str | None = None


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
