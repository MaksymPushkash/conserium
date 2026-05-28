from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class StatsTimelineBucket:
    month: str
    saved_documents: int
    active_documents: int
    query_count: int
    citation_count: int


@dataclass(frozen=True, slots=True)
class DailyDigestItemRecord:
    document_id: UUID
    title: str
    summary: str | None
    question: str
    reason: str
    last_used_at: datetime
    days_since_activity: int


@dataclass(frozen=True, slots=True)
class WeeklyReportRecord:
    saved_documents: int
    active_documents: int
    query_count: int
    citation_count: int
    ready_documents: int
    failed_documents: int
    stale_documents: int


@dataclass(frozen=True, slots=True)
class StatsOverviewRecord:
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


class IStatsRepository(ABC):
    @abstractmethod
    async def get_overview(self, *, user_id: UUID) -> StatsOverviewRecord: ...

    @abstractmethod
    async def get_learning_timeline(self, *, user_id: UUID, months: int) -> list[StatsTimelineBucket]: ...

    @abstractmethod
    async def get_daily_digest_items(self, *, user_id: UUID, limit: int = 3) -> list[DailyDigestItemRecord]: ...

    @abstractmethod
    async def get_weekly_report(self, *, user_id: UUID) -> WeeklyReportRecord: ...
