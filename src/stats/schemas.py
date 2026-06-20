from datetime import datetime
from uuid import UUID

from src.kit.schemas import Schema


class StatsOverviewResponse(Schema):
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


class StatsTimelineBucketResponse(Schema):
    month: str
    saved_documents: int
    active_documents: int
    query_count: int
    citation_count: int


class StatsTimelineResponse(Schema):
    items: list[StatsTimelineBucketResponse]
    months: int


class DailyDigestItemResponse(Schema):
    document_id: UUID
    title: str
    summary: str | None
    question: str
    reason: str
    last_used_at: datetime
    days_since_activity: int


class DailyDigestResponse(Schema):
    items: list[DailyDigestItemResponse]


class WeeklyReportResponse(Schema):
    saved_documents: int
    active_documents: int
    query_count: int
    citation_count: int
    ready_documents: int
    failed_documents: int
    stale_documents: int
    summary: str
    recommended_actions: list[str]


__all__ = [
    "DailyDigestItemResponse",
    "DailyDigestResponse",
    "StatsOverviewResponse",
    "StatsTimelineBucketResponse",
    "StatsTimelineResponse",
    "WeeklyReportResponse",
]
