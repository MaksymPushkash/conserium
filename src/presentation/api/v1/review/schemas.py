from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GenerateFlashcardsRequest(BaseModel):
    document_id: UUID | None = None
    collection_id: UUID | None = None
    topic: str | None = Field(default=None, max_length=120)
    limit: int = Field(default=5, ge=1, le=20)


class ReviewFlashcardRequest(BaseModel):
    grade: str = Field(pattern="^(again|hard|good|easy)$")


class FlashcardResponse(BaseModel):
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


class FlashcardListResponse(BaseModel):
    items: list[FlashcardResponse]
    total: int
    limit: int


class GenerateFlashcardsResponse(BaseModel):
    items: list[FlashcardResponse]
    created_count: int
