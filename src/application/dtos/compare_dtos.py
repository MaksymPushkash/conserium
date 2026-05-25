from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.application.dtos.query_dtos import QuerySourceDTO


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
