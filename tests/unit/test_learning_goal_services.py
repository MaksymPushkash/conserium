from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest

from src.integrations.schemas import FetchedWebResource
from src.kit.exceptions import ResourceNotFoundException, ValidationException
from src.learning_goals.repository import LearningGoalRecord, LearningGoalRepository, LearningGoalResourceRecord
from src.learning_goals.schemas import (
    LearningGoalRequest,
    LearningGoalUpdateRequest,
)
from src.learning_goals.service import LearningGoalService
from src.topics.repository import TopicDetailRecord, TopicDocumentRecord, TopicRecord, TopicRepository

if TYPE_CHECKING:
    from src.integrations.web_resource_fetcher import HTTPWebResourceFetcher


class _FakeLearningGoalRepository:
    def __init__(self, records: list[LearningGoalRecord] | None = None) -> None:
        self.records = records or []
        self.cached_resources: dict[UUID, list[LearningGoalResourceRecord]] = {}
        self.deleted_id: UUID | None = None

    async def list_by_user_id(self, user_id: UUID) -> list[LearningGoalRecord]:
        return [record for record in self.records if record.user_id == user_id]

    async def get_by_id(self, goal_id: UUID) -> LearningGoalRecord | None:
        return next((record for record in self.records if record.id == goal_id), None)

    async def create(
        self,
        *,
        goal_id: UUID,
        user_id: UUID,
        topic: str,
        description: str | None,
        target_date: date | None,
    ) -> LearningGoalRecord:
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
    ) -> LearningGoalRecord:
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
    ) -> list[LearningGoalResourceRecord]:
        return [
            resource
            for resource in self.cached_resources.get(goal_id, [])
            if resource.refreshed_at >= refreshed_after
        ]

    async def replace_cached_resources(
        self,
        *,
        goal_id: UUID,
        resources: list[LearningGoalResourceRecord],
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


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def flush(self) -> None:
        self.committed = True


class _FakeWebResourceFetcher:
    def __init__(self) -> None:
        self.fetch_count = 0

    async def fetch(self, url: str) -> FetchedWebResource | None:
        self.fetch_count += 1
        return FetchedWebResource(title="Python Tutorial", excerpt=f"Fetched {url}")


class _PartiallyFailingWebResourceFetcher:
    def __init__(self) -> None:
        self.fetch_count = 0

    async def fetch(self, url: str) -> FetchedWebResource | None:
        self.fetch_count += 1
        if "tutorial" in url:
            raise RuntimeError("fetch failed")
        return FetchedWebResource(title="Fetched resource", excerpt=f"Fetched {url}")


def _goal_record(
    *,
    goal_id: UUID,
    user_id: UUID,
    topic: str,
    description: str | None = None,
    target_date: date | None = None,
    status: str = "active",
) -> LearningGoalRecord:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    return LearningGoalRecord(
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


def _patch_repositories(
    monkeypatch: pytest.MonkeyPatch,
    *,
    goals: _FakeLearningGoalRepository,
    topics: _FakeTopicRepository,
) -> None:
    monkeypatch.setattr(LearningGoalRepository, "from_session", classmethod(lambda cls, session: goals))
    monkeypatch.setattr(TopicRepository, "from_session", classmethod(lambda cls, session: topics))


@pytest.mark.asyncio
async def test_create_learning_goal_derives_progress_from_topic_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    goals = _FakeLearningGoalRepository()
    topics = _FakeTopicRepository(
        {
            "python": _topic_detail(
                "Python",
                _topic_document("Python generators", "yield and iterator examples"),
                _topic_document("Async Python", "asyncio concurrency notes"),
            )
        }
    )
    session = _FakeSession()
    _patch_repositories(monkeypatch, goals=goals, topics=topics)

    result = await LearningGoalService().create(
        session,
        user_id=user_id,
        body=LearningGoalRequest(topic=" Python ", description=" Learn it ", target_date=None),
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
    assert session.committed


@pytest.mark.asyncio
async def test_list_learning_goals_returns_zero_progress_without_topic_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    goal = _goal_record(goal_id=uuid4(), user_id=user_id, topic="Rust")
    _patch_repositories(
        monkeypatch,
        goals=_FakeLearningGoalRepository([goal]),
        topics=_FakeTopicRepository({}),
    )

    result = await LearningGoalService().list_goals(_FakeSession(), user_id=user_id)

    assert result[0].progress_ratio == 0
    assert result[0].missing_count > 0


@pytest.mark.asyncio
async def test_update_learning_goal_rejects_invalid_status(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    goal = _goal_record(goal_id=uuid4(), user_id=user_id, topic="Python")
    _patch_repositories(
        monkeypatch,
        goals=_FakeLearningGoalRepository([goal]),
        topics=_FakeTopicRepository({}),
    )

    with pytest.raises(ValidationException, match="invalid learning goal status"):
        await LearningGoalService().update(
            _FakeSession(),
            user_id=user_id,
            goal_id=goal.id,
            body=LearningGoalUpdateRequest.model_construct(status="done"),
        )


@pytest.mark.asyncio
async def test_delete_learning_goal_requires_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    goal = _goal_record(goal_id=uuid4(), user_id=uuid4(), topic="Python")
    _patch_repositories(
        monkeypatch,
        goals=_FakeLearningGoalRepository([goal]),
        topics=_FakeTopicRepository({}),
    )

    with pytest.raises(ResourceNotFoundException, match="learning goal not found"):
        await LearningGoalService().delete(_FakeSession(), user_id=uuid4(), goal_id=goal.id)


@pytest.mark.asyncio
async def test_rank_learning_goal_resources_fetches_live_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    goal = _goal_record(goal_id=uuid4(), user_id=user_id, topic="Python")
    goals = _FakeLearningGoalRepository([goal])
    _patch_repositories(monkeypatch, goals=goals, topics=_FakeTopicRepository({}))

    fetcher = _FakeWebResourceFetcher()
    result = await LearningGoalService().rank_resources(
        _FakeSession(),
        user_id=user_id,
        goal_id=goal.id,
        refresh=False,
        web_resource_fetcher=cast("HTTPWebResourceFetcher", fetcher),
    )

    assert result[0].title == "Python Tutorial"
    assert result[0].excerpt == "Fetched https://docs.python.org/3/tutorial/"
    assert result[0].score == 1.0
    assert result[0].warning is None
    assert result[0].cached is False
    assert result[0].refreshed_at is not None
    assert fetcher.fetch_count == 3
    assert goals.cached_resources[goal.id]


@pytest.mark.asyncio
async def test_rank_learning_goal_resources_uses_fresh_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    goal = _goal_record(goal_id=uuid4(), user_id=user_id, topic="Python")
    goals = _FakeLearningGoalRepository([goal])
    goals.cached_resources[goal.id] = [
        LearningGoalResourceRecord(
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
    _patch_repositories(monkeypatch, goals=goals, topics=_FakeTopicRepository({}))
    fetcher = _FakeWebResourceFetcher()

    result = await LearningGoalService().rank_resources(
        _FakeSession(),
        user_id=user_id,
        goal_id=goal.id,
        refresh=False,
        web_resource_fetcher=cast("HTTPWebResourceFetcher", fetcher),
    )

    assert result[0].title == "Cached resource"
    assert result[0].cached is True
    assert result[0].refreshed_at is not None
    assert fetcher.fetch_count == 0


@pytest.mark.asyncio
async def test_rank_learning_goal_resources_keeps_results_when_one_fetch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    goal = _goal_record(goal_id=uuid4(), user_id=user_id, topic="Python")
    goals = _FakeLearningGoalRepository([goal])
    _patch_repositories(monkeypatch, goals=goals, topics=_FakeTopicRepository({}))
    fetcher = _PartiallyFailingWebResourceFetcher()

    result = await LearningGoalService().rank_resources(
        _FakeSession(),
        user_id=user_id,
        goal_id=goal.id,
        refresh=True,
        web_resource_fetcher=cast("HTTPWebResourceFetcher", fetcher),
    )

    assert len(result) == 3
    assert any(resource.warning == "Resource refresh failed." for resource in result)
    assert goals.cached_resources[goal.id]
