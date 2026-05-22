from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

if TYPE_CHECKING:
    from datetime import date, datetime
    from uuid import UUID

    from src.application.dtos.knowledge_gap_dtos import KnowledgeGapAreaDTO


@final
@dataclass(frozen=True, slots=True)
class SuggestedLearningResourceDTO:
    area: str
    title: str
    search_query: str
    reason: str
    url: str | None = None


@final
@dataclass(frozen=True, slots=True)
class RankedLearningResourceDTO:
    area: str
    title: str
    search_query: str
    reason: str
    url: str | None
    excerpt: str | None
    score: float
    warning: str | None = None
    cached: bool = False
    refreshed_at: datetime | None = None


@final
@dataclass(frozen=True, slots=True)
class LearningGoalResourceRecordDTO:
    goal_id: UUID
    area: str
    title: str
    search_query: str
    reason: str
    url: str | None
    excerpt: str | None
    score: float
    refreshed_at: datetime


@final
@dataclass(frozen=True, slots=True)
class LearningGoalDTO:
    id: UUID
    user_id: UUID
    topic: str
    description: str | None
    target_date: date | None
    status: str
    progress_ratio: float
    covered_count: int
    missing_count: int
    gaps: list[KnowledgeGapAreaDTO]
    recommended_next_areas: list[str]
    suggested_resources: list[SuggestedLearningResourceDTO]
    deadline_status: str
    days_remaining: int | None
    created_at: datetime
    updated_at: datetime | None


@final
@dataclass(frozen=True, slots=True)
class LearningGoalRecordDTO:
    id: UUID
    user_id: UUID
    topic: str
    description: str | None
    target_date: date | None
    status: str
    created_at: datetime
    updated_at: datetime | None


@final
@dataclass(frozen=True, slots=True)
class CreateLearningGoalDTO:
    user_id: UUID
    topic: str
    description: str | None = None
    target_date: date | None = None


@final
@dataclass(frozen=True, slots=True)
class UpdateLearningGoalDTO:
    user_id: UUID
    goal_id: UUID
    topic: str | None = None
    description: str | None = None
    target_date: date | None = None
    status: str | None = None
