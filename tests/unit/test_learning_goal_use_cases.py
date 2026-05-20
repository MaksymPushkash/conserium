from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest

from src.application.dtos.learning_goal_dtos import (
    CreateLearningGoalDTO,
    LearningGoalRecordDTO,
    LearningGoalResourceRecordDTO,
    UpdateLearningGoalDTO,
)
from src.application.ports.integrations.web_resource_fetcher import FetchedWebResource
from src.application.ports.persistence.topic_repository import TopicDetailRecord, TopicDocumentRecord, TopicRecord
from src.application.use_cases.learning_goals import (
    CreateLearningGoalUseCase,
    DeleteLearningGoalUseCase,
    ListLearningGoalsUseCase,
    RankLearningGoalResourcesUseCase,
    UpdateLearningGoalUseCase,
)
from src.domain.exceptions import ResourceNotFoundException, ValidationException

if TYPE_CHECKING:
    from src.application.ports.integrations.web_resource_fetcher import IWebResourceFetcher
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class _FakeLearningGoalRepository:
    def __init__(self, records: list[LearningGoalRecordDTO] | None = None) -> None:
        self.records = records or []
        self.cached_resources: dict[UUID, list[LearningGoalResourceRecordDTO]] = {}
        self.deleted_id: UUID | None = None

    async def list_by_user_id(self, user_id: UUID) -> list[LearningGoalRecordDTO]:
        return [record for record in self.records if record.user_id == user_id]

    async def get_by_id(self, goal_id: UUID) -> LearningGoalRecordDTO | None:
        return next((record for record in self.records if record.id == goal_id), None)

    async def create(
        self,
        *,
        goal_id: UUID,
        user_id: UUID,
        topic: str,
        description: str | None,
        target_date: date | None,
    ) -> LearningGoalRecordDTO:
        record = _goal_record(goal_id=goal_id, user_id=user_id, topic=topic, description=description, target_date=target_date)
        self.records.append(record)
        return record

    async def update(
        self,
        *,
        goal_id: UUID,
        topic: str,
        description: str | None,
        target_date: date | None,
        status: str,
    ) -> LearningGoalRecordDTO:
        existing = next(record for record in self.records if record.id == goal_id)
        updated = _goal_record(
            goal_id=existing.id,
            user_id=existing.user_id,
            topic=topic,
            description=description,
            target_date=target_date,
            status=status,
        )
        self.records = [updated if record.id == goal_id else record for record in self.records]
        return updated

    async def delete(self, goal_id: UUID) -> None:
        self.deleted_id = goal_id
        self.records = [record for record in self.records if record.id != goal_id]
        await self.delete_cached_resources(goal_id)

    async def list_cached_resources(
        self,
        *,
        goal_id: UUID,
        refreshed_after: datetime,
    ) -> list[LearningGoalResourceRecordDTO]:
        return [
            resource
            for resource in self.cached_resources.get(goal_id, [])
            if resource.refreshed_at >= refreshed_after
        ]

    async def replace_cached_resources(
        self,
        *,
        goal_id: UUID,
        resources: list[LearningGoalResourceRecordDTO],
    ) -> None:
        self.cached_resources[goal_id] = resources

    async def delete_cached_resources(self, goal_id: UUID) -> None:
        self.cached_resources.pop(goal_id, None)


class _FakeTopicRepository:
    def __init__(self, details: dict[str, TopicDetailRecord]) -> None:
        self.details = details

    async def get_detail_by_name(self, user_id: UUID, *, name: str, document_limit: int) -> TopicDetailRecord | None:
        return self.details.get(name.casefold())

    async def get_details_by_names(
        self,
        user_id: UUID,
        *,
        names: list[str],
        document_limit: int,
    ) -> dict[str, TopicDetailRecord]:
        return {
            name.casefold(): detail
            for name in names
            if (detail := self.details.get(name.casefold())) is not None
        }


class _FakeUnitOfWork:
    def __init__(self, goals: _FakeLearningGoalRepository, topics: _FakeTopicRepository) -> None:
        self.goals = goals
        self.learning_goal_repo = goals
        self.topic_repo = topics
        self.committed = False

    async def __aenter__(self) -> _FakeUnitOfWork:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        return None


class _FakeWebResourceFetcher:
    def __init__(self) -> None:
        self.fetch_count = 0

    async def fetch(self, url: str) -> FetchedWebResource | None:
        self.fetch_count += 1
        return FetchedWebResource(title="Python Tutorial", excerpt=f"Fetched {url}")


def _goal_record(
    *,
    goal_id: UUID,
    user_id: UUID,
    topic: str,
    description: str | None = None,
    target_date: date | None = None,
    status: str = "active",
) -> LearningGoalRecordDTO:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    return LearningGoalRecordDTO(
        id=goal_id,
        user_id=user_id,
        topic=topic,
        description=description,
        target_date=target_date,
        status=status,
        created_at=now,
        updated_at=None,
    )


def _topic_detail(name: str, *documents: TopicDocumentRecord) -> TopicDetailRecord:
    return TopicDetailRecord(
        topic=TopicRecord(name=name, document_count=len(documents), last_document_at=None),
        documents=list(documents),
    )


def _topic_document(title: str, summary: str | None) -> TopicDocumentRecord:
    return TopicDocumentRecord(
        id=uuid4(),
        title=title,
        type="TEXT",
        status="READY",
        summary=summary,
        created_at=datetime(2026, 5, 17, tzinfo=UTC),
    )


def _as_uow(uow: _FakeUnitOfWork) -> IUnitOfWork:
    return cast("IUnitOfWork", uow)


@pytest.mark.asyncio
async def test_create_learning_goal_derives_progress_from_topic_documents() -> None:
    user_id = uuid4()
    uow = _FakeUnitOfWork(
        _FakeLearningGoalRepository(),
        _FakeTopicRepository(
            {
                "python": _topic_detail(
                    "Python",
                    _topic_document("Python generators", "yield and iterator examples"),
                    _topic_document("Async Python", "asyncio concurrency notes"),
                )
            }
        ),
    )

    result = await CreateLearningGoalUseCase(_as_uow(uow))(
        CreateLearningGoalDTO(user_id=user_id, topic=" Python ", description=" Learn it ", target_date=None)
    )

    assert result.topic == "Python"
    assert result.description == "Learn it"
    assert result.covered_count == 2
    assert result.missing_count == 5
    assert result.recommended_next_areas == ["Syntax and data model", "OOP", "Testing"]
    assert [resource.area for resource in result.suggested_resources] == ["Syntax and data model", "OOP", "Testing"]
    assert result.suggested_resources[0].url == "https://docs.python.org/3/tutorial/"
    assert result.deadline_status == "none"
    assert result.days_remaining is None
    assert uow.committed


@pytest.mark.asyncio
async def test_list_learning_goals_returns_zero_progress_without_topic_documents() -> None:
    user_id = uuid4()
    goal = _goal_record(goal_id=uuid4(), user_id=user_id, topic="Rust")
    uow = _FakeUnitOfWork(_FakeLearningGoalRepository([goal]), _FakeTopicRepository({}))

    result = await ListLearningGoalsUseCase(_as_uow(uow))(user_id=user_id)

    assert result[0].progress_ratio == 0
    assert result[0].missing_count > 0


@pytest.mark.asyncio
async def test_update_learning_goal_rejects_invalid_status() -> None:
    user_id = uuid4()
    goal = _goal_record(goal_id=uuid4(), user_id=user_id, topic="Python")
    uow = _FakeUnitOfWork(_FakeLearningGoalRepository([goal]), _FakeTopicRepository({}))

    with pytest.raises(ValidationException, match="invalid learning goal status"):
        await UpdateLearningGoalUseCase(_as_uow(uow))(
            UpdateLearningGoalDTO(user_id=user_id, goal_id=goal.id, status="done")
        )


@pytest.mark.asyncio
async def test_delete_learning_goal_requires_owner() -> None:
    goal = _goal_record(goal_id=uuid4(), user_id=uuid4(), topic="Python")
    uow = _FakeUnitOfWork(_FakeLearningGoalRepository([goal]), _FakeTopicRepository({}))

    with pytest.raises(ResourceNotFoundException, match="learning goal not found"):
        await DeleteLearningGoalUseCase(_as_uow(uow))(user_id=uuid4(), goal_id=goal.id)


@pytest.mark.asyncio
async def test_rank_learning_goal_resources_fetches_live_metadata() -> None:
    user_id = uuid4()
    goal = _goal_record(goal_id=uuid4(), user_id=user_id, topic="Python")
    uow = _FakeUnitOfWork(_FakeLearningGoalRepository([goal]), _FakeTopicRepository({}))

    fetcher = _FakeWebResourceFetcher()
    result = await RankLearningGoalResourcesUseCase(_as_uow(uow), cast("IWebResourceFetcher", fetcher))(
        user_id=user_id,
        goal_id=goal.id,
    )

    assert result[0].title == "Python Tutorial"
    assert result[0].excerpt == "Fetched https://docs.python.org/3/tutorial/"
    assert result[0].score == 1.0
    assert result[0].cached is False
    assert result[0].refreshed_at is not None
    assert fetcher.fetch_count == 3
    assert uow.goals.cached_resources[goal.id]


@pytest.mark.asyncio
async def test_rank_learning_goal_resources_uses_fresh_cache() -> None:
    user_id = uuid4()
    goal = _goal_record(goal_id=uuid4(), user_id=user_id, topic="Python")
    goals = _FakeLearningGoalRepository([goal])
    goals.cached_resources[goal.id] = [
        LearningGoalResourceRecordDTO(
            goal_id=goal.id,
            area="Testing",
            title="Cached resource",
            search_query="python testing",
            reason="Cached reason",
            url="https://example.com",
            excerpt="Cached excerpt",
            score=0.9,
            refreshed_at=datetime.now(UTC),
        )
    ]
    uow = _FakeUnitOfWork(goals, _FakeTopicRepository({}))
    fetcher = _FakeWebResourceFetcher()

    result = await RankLearningGoalResourcesUseCase(_as_uow(uow), cast("IWebResourceFetcher", fetcher))(
        user_id=user_id,
        goal_id=goal.id,
    )

    assert result[0].title == "Cached resource"
    assert result[0].cached is True
    assert result[0].refreshed_at is not None
    assert fetcher.fetch_count == 0
