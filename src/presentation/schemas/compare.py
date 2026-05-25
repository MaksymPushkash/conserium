from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.presentation.schemas.query import QuerySourceResponse


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
