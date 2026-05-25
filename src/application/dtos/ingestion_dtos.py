from dataclasses import dataclass
from typing import TypedDict, final
from uuid import UUID

from src.domain.value_objects.document_type import DocumentType


class EntityDTO(TypedDict):
    text: str
    label: str


class CategoryDTO(TypedDict):
    label: str
    score: float


@final
@dataclass(frozen=True, slots=True)
class TextChunkDTO:
    content: str
    chunk_index: int
    start_char: int
    end_char: int
    token_count: int


@final
@dataclass(frozen=True, slots=True)
class IngestTextDocumentDTO:
    user_id: UUID
    title: str
    raw_text: str
    collection_id: UUID | None = None
    type: DocumentType = DocumentType.TEXT
    source_url: str | None = None
    language: str | None = None


@final
@dataclass(frozen=True, slots=True)
class IngestDocumentDTO:
    user_id: UUID
    title: str
    type: DocumentType
    collection_id: UUID | None = None
    tags: list[str] | None = None
    source_url: str | None = None
    file_path: str | None = None
    file_size_bytes: int | None = None
    raw_content: str | None = None
    language: str | None = None
