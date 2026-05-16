from dataclasses import dataclass
from uuid import UUID

from src.application.dtos.query_dtos import QuerySourceDTO
from src.domain.value_objects.document_type import DocumentType


@dataclass(frozen=True, slots=True)
class DraftGenerateDTO:
    user_id: UUID
    prompt: str
    collection_id: UUID | None = None
    tag_names: tuple[str, ...] | None = None
    document_types: tuple[DocumentType, ...] | None = None
    limit: int = 8


@dataclass(frozen=True, slots=True)
class DraftResultDTO:
    prompt: str
    markdown: str
    sources: list[QuerySourceDTO]
    gaps: list[str]
