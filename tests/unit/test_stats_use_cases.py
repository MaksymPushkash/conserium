import uuid
from typing import TYPE_CHECKING, cast

from src.application.ports.persistence.document_activity_repository import DocumentActivityOverview
from src.application.ports.persistence.stats_repository import StatsTimelineBucket
from src.application.use_cases.stats import GetStatsOverviewUseCase
from src.application.use_cases.stats.get_stats_timeline_use_case import GetStatsTimelineUseCase
from src.domain.value_objects.document_status import DocumentStatus

if TYPE_CHECKING:
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class _FakeDocumentRepository:
    def __init__(self) -> None:
        self.counts = {
            None: 8,
            DocumentStatus.READY: 5,
            DocumentStatus.FAILED: 1,
            DocumentStatus.PENDING: 1,
            DocumentStatus.QUEUED: 1,
            DocumentStatus.PROCESSING: 0,
        }

    async def count_by_user_id(
        self,
        user_id: uuid.UUID,
        *,
        document_type: object | None = None,
        collection_id: uuid.UUID | None = None,
        status: DocumentStatus | None = None,
    ) -> int:
        return self.counts[status]


class _FakeDocumentActivityRepository:
    async def summarize_user_overview(self, *, user_id: uuid.UUID) -> DocumentActivityOverview:
        return DocumentActivityOverview(
            hot_documents=3,
            cold_documents=2,
            forgotten_documents=1,
            active_documents=6,
            query_count=11,
            citation_count=7,
        )


class _FakeUnitOfWork:
    def __init__(self) -> None:
        self.document_repo = _FakeDocumentRepository()
        self.document_activity_repo = _FakeDocumentActivityRepository()
        self.stats_repo = _FakeStatsRepository()

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


async def test_stats_overview_counts_documents_and_activity() -> None:
    use_case = GetStatsOverviewUseCase(cast("IUnitOfWork", _FakeUnitOfWork()))

    result = await use_case(uuid.uuid4())

    assert result.total_documents == 8
    assert result.ready_documents == 5
    assert result.processing_documents == 2
    assert result.failed_documents == 1
    assert result.hot_documents == 3
    assert result.cold_documents == 2
    assert result.forgotten_documents == 1
    assert result.active_documents == 6
    assert result.query_count == 11
    assert result.citation_count == 7


class _FakeStatsRepository:
    async def get_learning_timeline(self, *, user_id: uuid.UUID, months: int) -> list[StatsTimelineBucket]:
        return [
            StatsTimelineBucket(
                month="2026-04",
                saved_documents=2,
                active_documents=1,
                query_count=4,
                citation_count=3,
            ),
            StatsTimelineBucket(
                month="2026-05",
                saved_documents=3,
                active_documents=2,
                query_count=5,
                citation_count=4,
            ),
        ]


async def test_stats_timeline_returns_monthly_buckets() -> None:
    use_case = GetStatsTimelineUseCase(cast("IUnitOfWork", _FakeUnitOfWork()))

    result = await use_case(uuid.uuid4(), months=2)

    assert result.months == 2
    assert [item.month for item in result.items] == ["2026-04", "2026-05"]
    assert result.items[0].saved_documents == 2
    assert result.items[1].query_count == 5
