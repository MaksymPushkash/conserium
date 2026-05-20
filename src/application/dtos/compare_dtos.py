from dataclasses import dataclass
from uuid import UUID

from src.application.dtos.query_dtos import QuerySourceDTO


@dataclass(frozen=True, slots=True)
class CompareDocumentsDTO:
    user_id: UUID
    left_document_id: UUID
    right_document_id: UUID
    prompt: str | None = None
    limit: int = 12


@dataclass(frozen=True, slots=True)
class CompareResultDTO:
    left_document_id: UUID
    right_document_id: UUID
    left_title: str
    right_title: str
    markdown: str
    sources: list[QuerySourceDTO]
