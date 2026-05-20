from __future__ import annotations

from datetime import date, datetime  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, Field

from src.presentation.schemas.knowledge_gap import KnowledgeGapAreaResponse  # noqa: TC001


class LearningGoalRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    target_date: date | None = None


class LearningGoalUpdateRequest(BaseModel):
    topic: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    target_date: date | None = None
    status: str | None = Field(default=None, pattern="^(active|paused|completed)$")


class SuggestedLearningResourceResponse(BaseModel):
    area: str
    title: str
    search_query: str
    reason: str
    url: str | None


class RankedLearningResourceResponse(BaseModel):
    area: str
    title: str
    search_query: str
    reason: str
    url: str | None
    excerpt: str | None
    score: float
    cached: bool
    refreshed_at: datetime | None


class LearningGoalResponse(BaseModel):
    id: UUID
    user_id: UUID
    topic: str
    description: str | None
    target_date: date | None
    status: str
    progress_ratio: float
    covered_count: int
    missing_count: int
    gaps: list[KnowledgeGapAreaResponse]
    recommended_next_areas: list[str]
    suggested_resources: list[SuggestedLearningResourceResponse]
    deadline_status: str
    days_remaining: int | None
    created_at: datetime
    updated_at: datetime | None
