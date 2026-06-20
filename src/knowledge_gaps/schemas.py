from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.documents.status import DocumentStatus


@dataclass(frozen=True, slots=True)
class KnowledgeGapAreaDTO:
    id: str
    name: str
    covered: bool
    evidence_count: int
    evidence_titles: list[str]
    why_detected: str
    missing_source_types: list[str]
    severity: str
    rationale: str
    suggested_actions: list[str]


@dataclass(frozen=True, slots=True)
class KnowledgeGapDTO:
    id: str
    topic: str
    collection_id: UUID | None
    covered_count: int
    missing_count: int
    coverage_ratio: float
    why_detected: str
    missing_source_types: list[str]
    severity: str
    rationale: str
    suggested_actions: list[str]
    areas: list[KnowledgeGapAreaDTO]


@dataclass(frozen=True, slots=True)
class KnowledgeGapListDTO:
    items: list[KnowledgeGapDTO]
    total: int


class KnowledgeGapAreaResponse(BaseModel):
    id: str
    name: str
    covered: bool
    evidence_count: int
    evidence_titles: list[str] = Field(default_factory=list)
    why_detected: str
    missing_source_types: list[str] = Field(default_factory=list)
    severity: str
    rationale: str
    suggested_actions: list[str] = Field(default_factory=list)


class KnowledgeGapResponse(BaseModel):
    id: str
    topic: str
    collection_id: str | None = None
    covered_count: int
    missing_count: int
    coverage_ratio: float
    why_detected: str
    missing_source_types: list[str] = Field(default_factory=list)
    severity: str
    rationale: str
    suggested_actions: list[str] = Field(default_factory=list)
    areas: list[KnowledgeGapAreaResponse] = Field(default_factory=list)


class KnowledgeGapListResponse(BaseModel):
    items: list[KnowledgeGapResponse]
    total: int


class KnowledgeGapNoteRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=100)
    area_name: str = Field(min_length=1, max_length=100)
    collection_id: str | None = None


class NoteResponse(BaseModel):
    id: UUID
    collection_id: UUID | None
    title: str
    content: str
    status: DocumentStatus
    word_count: int
    language: str | None
    created_at: datetime
    updated_at: datetime | None
