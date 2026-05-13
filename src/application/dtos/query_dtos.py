from dataclasses import dataclass
from typing import final
from uuid import UUID

from src.application.dtos.refrag_dtos import RefragContextPackage
from src.domain.value_objects.document_type import DocumentType


@final
@dataclass(frozen=True, slots=True)
class QueryDTO:
    user_id: UUID
    query: str
    conversation_id: UUID | None = None
    collection_id: UUID | None = None
    document_types: tuple[DocumentType, ...] | None = None
    limit: int = 5


@final
@dataclass(frozen=True, slots=True)
class QuerySourceDTO:
    chunk_id: UUID
    document_id: UUID
    document_title: str | None
    content: str
    page_number: int | None
    chunk_index: int
    score: float | None = None
    used_in_answer: bool = False


@final
@dataclass(frozen=True, slots=True)
class QueryResultDTO:
    conversation_id: UUID
    query: str
    answer: str
    sources: list[QuerySourceDTO]
    refrag_context: RefragContextPackage
