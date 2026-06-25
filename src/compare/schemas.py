from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.query.schemas import QuerySource, QuerySourceResponse


@dataclass(frozen=True, slots=True)
class CompareEvidence:
    dimension: str
    left_evidence: str | None
    right_evidence: str | None
    assessment: str
    left_source_id: UUID | None = None
    right_source_id: UUID | None = None
    left_citation: str | None = None
    right_citation: str | None = None
    confidence: float | None = None
    rationale: str | None = None
    grounding_type: str = "structured"


@dataclass(frozen=True, slots=True)
class CompareResult:
    id: UUID
    user_id: UUID
    collection_id: UUID | None
    left_document_id: UUID
    right_document_id: UUID
    left_title: str
    right_title: str
    dimensions: list[str]
    markdown: str
    summary: str
    evidence_rows: list[CompareEvidence]
    sources: list[QuerySource]
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CompareListResult:
    items: list[CompareResult]
    total: int


class CompareDocumentsRequest(BaseModel):
    left_document_id: UUID
    right_document_id: UUID
    prompt: str | None = Field(default=None, max_length=1000)
    dimensions: list[str] | None = Field(default=None, max_length=6)
    limit: int = Field(default=12, ge=2, le=30)


class CompareEvidenceRowResponse(BaseModel):
    dimension: str
    left_evidence: str | None
    right_evidence: str | None
    assessment: str
    left_source_id: UUID | None = None
    right_source_id: UUID | None = None
    left_citation: str | None = None
    right_citation: str | None = None
    confidence: float | None = None
    rationale: str | None = None
    grounding_type: str = "structured"


class CompareDocumentsResponse(BaseModel):
    id: UUID
    collection_id: UUID | None
    left_document_id: UUID
    right_document_id: UUID
    left_title: str
    right_title: str
    dimensions: list[str]
    markdown: str
    summary: str
    evidence_rows: list[CompareEvidenceRowResponse]
    sources: list[QuerySourceResponse]
    created_at: datetime | None = None


class CompareListResponse(BaseModel):
    items: list[CompareDocumentsResponse]
    total: int
