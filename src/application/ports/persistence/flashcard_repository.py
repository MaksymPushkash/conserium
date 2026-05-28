from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class FlashcardRecord:
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
    source_title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class FlashcardReviewRecord:
    id: UUID
    flashcard_id: UUID
    user_id: UUID
    grade: str
    previous_interval_days: int
    next_interval_days: int
    previous_ease_factor: float
    next_ease_factor: float
    reviewed_at: datetime


class IFlashcardRepository(ABC):
    @abstractmethod
    async def create_many(self, records: list[FlashcardRecord]) -> list[FlashcardRecord]: ...

    @abstractmethod
    async def list_due(self, *, user_id: UUID, now: datetime, limit: int = 20) -> list[FlashcardRecord]: ...

    @abstractmethod
    async def count_due(self, *, user_id: UUID, now: datetime) -> int: ...

    @abstractmethod
    async def get_by_id(self, flashcard_id: UUID) -> FlashcardRecord | None: ...

    @abstractmethod
    async def update_schedule(
        self,
        *,
        flashcard_id: UUID,
        due_at: datetime,
        interval_days: int,
        ease_factor: float,
        review_count: int,
    ) -> FlashcardRecord: ...

    @abstractmethod
    async def create_review(self, record: FlashcardReviewRecord) -> None: ...

    @abstractmethod
    async def existing_questions_for_document(self, *, user_id: UUID, document_id: UUID) -> set[str]: ...
