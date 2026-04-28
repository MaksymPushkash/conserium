from dataclasses import dataclass
from typing import final
from uuid import UUID

from src.domain.value_objects.document_type import DocumentType


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
