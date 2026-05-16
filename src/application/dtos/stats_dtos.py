from dataclasses import dataclass


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
