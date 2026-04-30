from dataclasses import dataclass
from enum import StrEnum
from typing import final
from uuid import UUID


class RefragRepresentation(StrEnum):
    FULL_TEXT = "FULL_TEXT"
    COMPRESSED = "COMPRESSED"
    DISCARDED = "DISCARDED"


@final
@dataclass(frozen=True, slots=True)
class RefragChunk:
    chunk_id: UUID
    document_id: UUID
    document_title: str | None
    original_text: str
    context_text: str
    representation: RefragRepresentation
    page_number: int | None
    chunk_index: int
    score: float | None
    original_token_count: int
    context_token_count: int


@final
@dataclass(frozen=True, slots=True)
class RefragContextPackage:
    query: str
    full_text_chunks: list[RefragChunk]
    compressed_chunks: list[RefragChunk]
    discarded_chunks: list[RefragChunk]
    total_original_tokens: int
    total_context_tokens: int
    compression_strategy: str

    @property
    def selected_chunks(self) -> list[RefragChunk]:
        return [*self.full_text_chunks, *self.compressed_chunks]
