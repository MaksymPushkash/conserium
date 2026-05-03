from dataclasses import dataclass
from datetime import datetime
from typing import final
from uuid import UUID


@final
@dataclass(frozen=True, slots=True)
class ConversationSourceDTO:
    chunk_id: UUID
    document_id: UUID
    document_title: str | None
    page_number: int | None
    chunk_index: int
    score: float | None


@final
@dataclass(frozen=True, slots=True)
class ConversationTurnDTO:
    query: str
    answer: str
    sources: list[ConversationSourceDTO]
    created_at: datetime
