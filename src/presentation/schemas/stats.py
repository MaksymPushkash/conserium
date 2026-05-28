from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class StatsOverviewResponse(BaseModel):
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


class StatsTimelineBucketResponse(BaseModel):
    month: str
    saved_documents: int
    active_documents: int
    query_count: int
    citation_count: int


class StatsTimelineResponse(BaseModel):
    items: list[StatsTimelineBucketResponse]
    months: int


class DailyDigestItemResponse(BaseModel):
    document_id: UUID
    title: str
    summary: str | None
    question: str
    reason: str
    last_used_at: datetime
    days_since_activity: int


class DailyDigestResponse(BaseModel):
    items: list[DailyDigestItemResponse]


class WeeklyReportResponse(BaseModel):
    saved_documents: int
    active_documents: int
    query_count: int
    citation_count: int
    ready_documents: int
    failed_documents: int
    stale_documents: int
    summary: str
    recommended_actions: list[str]
