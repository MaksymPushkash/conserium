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
