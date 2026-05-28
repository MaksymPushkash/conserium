from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class StatsOverviewDTO:
    total_documents: int
    ready_documents: int
    processing_documents: int
    failed_documents: int
    hot_documents: int
    cold_documents: int
    forgotten_documents: int
    active_documents: int
    query_count: int
    citation_count: int


@dataclass(frozen=True, slots=True)
class StatsTimelineBucketDTO:
    month: str
    saved_documents: int
    active_documents: int
    query_count: int
    citation_count: int


@dataclass(frozen=True, slots=True)
class StatsTimelineDTO:
    items: list[StatsTimelineBucketDTO]
    months: int


@dataclass(frozen=True, slots=True)
class DailyDigestItemDTO:
    document_id: UUID
    title: str
    summary: str | None
    question: str
    reason: str
    last_used_at: datetime
    days_since_activity: int


@dataclass(frozen=True, slots=True)
class DailyDigestDTO:
    items: list[DailyDigestItemDTO]


@dataclass(frozen=True, slots=True)
class WeeklyReportDTO:
    saved_documents: int
    active_documents: int
    query_count: int
    citation_count: int
    ready_documents: int
    failed_documents: int
    stale_documents: int
    summary: str
    recommended_actions: list[str]
