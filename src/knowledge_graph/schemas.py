from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime  # noqa: TC003
from typing import Literal
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class KnowledgeGraphNode:
    id: str
    kind: Literal["topic", "document"]
    label: str
    detail: str | None = None
    collection_id: UUID | None = None
    summary: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    suggested_questions: list[str] | None = None
    source_names: tuple[str, ...] = ()
    is_pinned: bool = False
    is_ignored: bool = False


@dataclass(frozen=True, slots=True)
class KnowledgeGraphEdge:
    id: str
    source_id: str
    target_id: str
    relation_type: str
    label: str
    score: float


@dataclass(frozen=True, slots=True)
class KnowledgeGraphResult:
    nodes: list[KnowledgeGraphNode]
    edges: list[KnowledgeGraphEdge]


@dataclass(frozen=True, slots=True)
class KnowledgeGraphInsight:
    kind: str
    title: str
    description: str
    severity: str
    count: int
    nodes: list[KnowledgeGraphNode]


@dataclass(frozen=True, slots=True)
class KnowledgeGraphInsights:
    items: list[KnowledgeGraphInsight]


@dataclass(frozen=True, slots=True)
class KnowledgeGraphConcern:
    id: UUID
    user_id: UUID
    node_id: str | None
    node_kind: str | None
    node_label: str | None
    message: str
    status: str
    created_at: datetime


class KnowledgeGraphNodeResponse(BaseModel):
    id: str
    kind: Literal["topic", "document"]
    label: str
    detail: str | None
    collection_id: UUID | None = None
    summary: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    suggested_questions: list[str] | None = None
    source_names: list[str]
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
    nodes: list[KnowledgeGraphNodeResponse]


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
