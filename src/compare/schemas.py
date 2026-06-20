from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.query.schemas import QuerySourceDTO, QuerySourceResponse


@dataclass(frozen=True, slots=True)
class CompareDocumentsDTO:
    user_id: UUID
    left_document_id: UUID
    right_document_id: UUID
    prompt: str | None = None
    dimensions: tuple[str, ...] | None = None
    limit: int = 12


@dataclass(frozen=True, slots=True)
class CompareEvidenceRowDTO:
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
class CompareResultDTO:
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
    evidence_rows: list[CompareEvidenceRowDTO]
    sources: list[QuerySourceDTO]
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CompareListDTO:
    items: list[CompareResultDTO]
    total: int


@dataclass(frozen=True, slots=True)
class ListCompareResultsDTO:
    user_id: UUID
    collection_id: UUID | None = None
    limit: int = 20
    offset: int = 0


@dataclass(frozen=True, slots=True)
class GetCompareResultDTO:
    user_id: UUID
    comparison_id: UUID


@dataclass(frozen=True, slots=True)
class DeleteCompareResultDTO:
    user_id: UUID
    comparison_id: UUID


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
