from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class KnowledgeGraphNodeDTO:
    id: str
    kind: str
    label: str
    detail: str | None = None
    collection_id: UUID | None = None
    summary: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    suggested_questions: list[str] | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeGraphEdgeDTO:
    id: str
    source_id: str
    target_id: str
    relation_type: str
    label: str
    score: float


@dataclass(frozen=True, slots=True)
class KnowledgeGraphDTO:
    nodes: list[KnowledgeGraphNodeDTO]
    edges: list[KnowledgeGraphEdgeDTO]


@dataclass(frozen=True, slots=True)
class KnowledgeGraphConcernDTO:
    id: UUID
    user_id: UUID
    node_id: str | None
    node_kind: str | None
    node_label: str | None
    message: str
    status: str
    created_at: datetime
