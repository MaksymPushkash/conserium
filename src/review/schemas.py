from __future__ import annotations

from datetime import datetime
from typing import Literal
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


class GenerateQuizRequest(BaseModel):
    document_id: UUID | None = None
    collection_id: UUID | None = None
    topic: str | None = Field(default=None, max_length=120)
    limit: int = Field(default=5, ge=1, le=20)


class QuizOptionResponse(BaseModel):
    id: str
    text: str


class QuizQuestionResponse(BaseModel):
    id: str
    question: str
    options: list[QuizOptionResponse]
    correct_option_id: str
    explanation: str
    weak_area: str
    source_document_id: UUID | None = None
    source_title: str | None = None


class QuizResponse(BaseModel):
    id: UUID
    user_id: UUID
    scope_type: str
    collection_id: UUID | None
    topic: str | None
    source_document_id: UUID | None
    title: str
    questions: list[QuizQuestionResponse]
    source_title: str | None
    created_at: datetime
    updated_at: datetime | None


class SubmitQuizAnswerRequest(BaseModel):
    question_id: str
    option_id: str


class SubmitQuizRequest(BaseModel):
    answers: list[SubmitQuizAnswerRequest] = Field(default_factory=list)


class QuizAttemptAnswerResponse(BaseModel):
    question_id: str
    option_id: str
    correct: bool
    correct_option_id: str
    weak_area: str | None = None


class QuizAttemptResponse(BaseModel):
    id: UUID
    quiz_id: UUID
    user_id: UUID
    answers: list[QuizAttemptAnswerResponse]
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


class LearningPathStepResponse(BaseModel):
    id: str
    title: str
    focus: str
    summary: str
    source_document_id: UUID | None = None
    status: Literal["todo", "done"]


class LearningPathResponse(BaseModel):
    id: UUID
    user_id: UUID
    scope_type: str
    collection_id: UUID | None
    topic: str | None
    source_document_id: UUID | None
    title: str
    steps: list[LearningPathStepResponse]
    created_at: datetime
    updated_at: datetime | None


class LearningPathListResponse(BaseModel):
    items: list[LearningPathResponse]
    total: int
    limit: int


class UpdateLearningPathStepRequest(BaseModel):
    status: str = Field(pattern="^(todo|done)$")
