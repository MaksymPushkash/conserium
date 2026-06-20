from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, Field


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
class GenerateQuizDTO:
    user_id: UUID
    document_id: UUID | None = None
    collection_id: UUID | None = None
    topic: str | None = None
    limit: int = 5


@dataclass(frozen=True, slots=True)
class SubmitQuizDTO:
    user_id: UUID
    quiz_id: UUID
    answers: list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class GenerateLearningPathDTO:
    user_id: UUID
    document_id: UUID | None = None
    collection_id: UUID | None = None
    topic: str | None = None
    limit: int = 6


@dataclass(frozen=True, slots=True)
class UpdateLearningPathStepDTO:
    user_id: UUID
    path_id: UUID
    step_id: str
    status: str


@dataclass(frozen=True, slots=True)
class RegenerateLearningPathDTO:
    user_id: UUID
    path_id: UUID
    limit: int = 6


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


class GenerateQuizRequest(BaseModel):
    document_id: UUID | None = None
    collection_id: UUID | None = None
    topic: str | None = Field(default=None, max_length=120)
    limit: int = Field(default=5, ge=1, le=20)


class QuizResponse(BaseModel):
    id: UUID
    user_id: UUID
    scope_type: str
    collection_id: UUID | None
    topic: str | None
    source_document_id: UUID | None
    title: str
    questions: list[dict[str, object]]
    source_title: str | None
    created_at: datetime
    updated_at: datetime | None


class SubmitQuizRequest(BaseModel):
    answers: list[dict[str, object]] = Field(default_factory=list)


class QuizAttemptResponse(BaseModel):
    id: UUID
    quiz_id: UUID
    user_id: UUID
    answers: list[dict[str, object]]
    score: int
    total: int
    weak_areas: list[str]
    created_at: datetime
    quiz_title: str | None = None


class QuizListResponse(BaseModel):
    items: list[QuizResponse]
    total: int
    limit: int


class QuizAttemptListResponse(BaseModel):
    items: list[QuizAttemptResponse]
    total: int
    limit: int


class QuizWeakAreaResponse(BaseModel):
    name: str
    count: int
    last_seen_at: datetime


class QuizWeakAreaListResponse(BaseModel):
    items: list[QuizWeakAreaResponse]
    total: int
    limit: int


class GenerateLearningPathRequest(BaseModel):
    document_id: UUID | None = None
    collection_id: UUID | None = None
    topic: str | None = Field(default=None, max_length=120)
    limit: int = Field(default=6, ge=1, le=12)


class LearningPathResponse(BaseModel):
    id: UUID
    user_id: UUID
    scope_type: str
    collection_id: UUID | None
    topic: str | None
    source_document_id: UUID | None
    title: str
    steps: list[dict[str, object]]
    created_at: datetime
    updated_at: datetime | None


class LearningPathListResponse(BaseModel):
    items: list[LearningPathResponse]
    total: int
    limit: int


class UpdateLearningPathStepRequest(BaseModel):
    status: str = Field(pattern="^(todo|done)$")
