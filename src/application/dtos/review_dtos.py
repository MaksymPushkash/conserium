from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GenerateFlashcardsDTO:
    user_id: UUID
    document_id: UUID | None = None
    collection_id: UUID | None = None
    topic: str | None = None
    limit: int = 5


@dataclass(frozen=True, slots=True)
class ReviewFlashcardDTO:
    user_id: UUID
    flashcard_id: UUID
    grade: str


@dataclass(frozen=True, slots=True)
class FlashcardDTO:
    id: UUID
    user_id: UUID
    scope_type: str
    collection_id: UUID | None
    topic: str | None
    source_document_id: UUID | None
    source_chunk_id: UUID | None
    question: str
    answer: str
    citation_metadata: dict[str, object]
    due_at: datetime
    interval_days: int
    ease_factor: float
    review_count: int
    source_title: str | None
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class FlashcardListDTO:
    items: list[FlashcardDTO]
    total: int
    limit: int


@dataclass(frozen=True, slots=True)
class GenerateFlashcardsResultDTO:
    items: list[FlashcardDTO]
    created_count: int
