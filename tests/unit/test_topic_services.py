import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from src.kit.exceptions import ResourceNotFoundException
from src.postgres import AsyncSession
from src.topics.repository import (
    TopicDetailRecord,
    TopicDocumentRecord,
    TopicOverrideEventRecord,
    TopicOverrideRecord,
    TopicRecord,
    TopicRepository,
    merge_topic_overrides,
)
from src.topics.service import TopicService
from src.topics.services.topic_builder import topic_names_from_tags

if TYPE_CHECKING:
    from pytest import MonkeyPatch


class _FakeTopicRepository:
    def __init__(self) -> None:
        self.detail: TopicDetailRecord | None = TopicDetailRecord(
            topic=TopicRecord(name="python", document_count=1, last_document_at=datetime(2026, 5, 1, tzinfo=UTC)),
            documents=[
                TopicDocumentRecord(
                    id=uuid.uuid4(),
                    title="Python Async",
                    type="TEXT",
                    status="READY",
                    summary="Async Python notes.",
                    created_at=datetime(2026, 5, 1, tzinfo=UTC),
                )
            ],
        )
        self.received_detail: tuple[uuid.UUID, str, int] | None = None
        self.received_rename: tuple[uuid.UUID, str, str] | None = None
        self.received_merge: tuple[uuid.UUID, list[str], str] | None = None
        self.received_pinned: tuple[uuid.UUID, str, bool] | None = None
        self.received_ignored: tuple[uuid.UUID, str, bool] | None = None
        self.received_events: tuple[uuid.UUID, str, int] | None = None

    async def list_by_user_id(self, user_id: uuid.UUID, *, limit: int, offset: int) -> list[TopicRecord]:
        return [
            TopicRecord(name="python", document_count=3, last_document_at=datetime(2026, 5, 1, tzinfo=UTC)),
            TopicRecord(name="async", document_count=2, last_document_at=datetime(2026, 4, 1, tzinfo=UTC)),
        ][offset : offset + limit]

    async def count_by_user_id(self, user_id: uuid.UUID) -> int:
        return 2

    async def get_detail_by_name(
        self,
        user_id: uuid.UUID,
        *,
        name: str,
        document_limit: int,
    ) -> TopicDetailRecord | None:
        self.received_detail = (user_id, name, document_limit)
        return self.detail

    async def list_override_events(
        self,
        *,
        user_id: uuid.UUID,
        topic_name: str,
        limit: int,
    ) -> list[TopicOverrideEventRecord]:
        self.received_events = (user_id, topic_name, limit)
        return []

    async def rename_topic(self, *, user_id: uuid.UUID, source_name: str, display_name: str) -> TopicRecord:
        self.received_rename = (user_id, source_name, display_name)
        return TopicRecord(name=display_name, document_count=1, last_document_at=None, source_names=(source_name,))

    async def merge_topics(self, *, user_id: uuid.UUID, source_names: list[str], display_name: str) -> TopicRecord:
        self.received_merge = (user_id, source_names, display_name)
        return TopicRecord(name=display_name, document_count=2, last_document_at=None, source_names=tuple(source_names))

    async def set_pinned(self, *, user_id: uuid.UUID, name: str, pinned: bool) -> TopicRecord:
        self.received_pinned = (user_id, name, pinned)
        return TopicRecord(name=name, document_count=1, last_document_at=None, source_names=(name,), pinned=pinned)

    async def set_ignored(self, *, user_id: uuid.UUID, name: str, ignored: bool) -> TopicRecord:
        self.received_ignored = (user_id, name, ignored)
        return TopicRecord(name=name, document_count=1, last_document_at=None, source_names=(name,), ignored=ignored)


class _FakeSession(AsyncSession):
    pass


def _set_topic_repository(monkeypatch: "MonkeyPatch", repository: _FakeTopicRepository) -> None:
    monkeypatch.setattr(TopicRepository, "from_session", classmethod(lambda cls, session: repository))


async def test_list_topics_returns_paginated_topic_groups(monkeypatch: "MonkeyPatch") -> None:
    _set_topic_repository(monkeypatch, _FakeTopicRepository())

    result = await TopicService().list_topics(_FakeSession(), user_id=uuid.uuid4(), limit=1, offset=0)

    assert result.total == 2
    assert result.limit == 1
    assert result.offset == 0
    assert result.items[0].name == "python"
    assert result.items[0].document_count == 3


async def test_get_topic_detail_returns_representative_documents(monkeypatch: "MonkeyPatch") -> None:
    repository = _FakeTopicRepository()
    _set_topic_repository(monkeypatch, repository)
    user_id = uuid.uuid4()

    result = await TopicService().get_detail(_FakeSession(), user_id=user_id, name=" Python ", document_limit=5)

    assert result.topic.name == "python"
    assert result.documents[0].title == "Python Async"
    assert repository.received_detail == (user_id, "python", 5)
    assert repository.received_events == (user_id, "python", 10)


async def test_get_topic_detail_raises_when_topic_is_missing(monkeypatch: "MonkeyPatch") -> None:
    repository = _FakeTopicRepository()
    repository.detail = None
    _set_topic_repository(monkeypatch, repository)

    with pytest.raises(ResourceNotFoundException):
        await TopicService().get_detail(_FakeSession(), user_id=uuid.uuid4(), name="missing", document_limit=5)


def test_topic_names_from_tags_limits_topic_count() -> None:
    tags = [f"tag-{index}" for index in range(10)]

    result = topic_names_from_tags(tags)

    assert result == tags[:8]


async def test_rename_topic_persists_display_override(monkeypatch: "MonkeyPatch") -> None:
    repository = _FakeTopicRepository()
    _set_topic_repository(monkeypatch, repository)
    user_id = uuid.uuid4()

    result = await TopicService().rename(_FakeSession(), user_id=user_id, name=" Python ", display_name="Backend")

    assert result.name == "Backend"
    assert result.source_names == ["Python"]
    assert repository.received_rename == (user_id, "Python", "Backend")


async def test_merge_topics_persists_source_aliases(monkeypatch: "MonkeyPatch") -> None:
    repository = _FakeTopicRepository()
    _set_topic_repository(monkeypatch, repository)
    user_id = uuid.uuid4()

    result = await TopicService().merge(
        _FakeSession(),
        user_id=user_id,
        name="Backend",
        source_names=["python", "fastapi"],
    )

    assert result.name == "Backend"
    assert result.source_names == ["python", "fastapi", "Backend"]
    assert repository.received_merge == (user_id, ["python", "fastapi", "Backend"], "Backend")


async def test_pin_and_ignore_topics_persist_flags(monkeypatch: "MonkeyPatch") -> None:
    repository = _FakeTopicRepository()
    _set_topic_repository(monkeypatch, repository)
    user_id = uuid.uuid4()

    pinned = await TopicService().pin(_FakeSession(), user_id=user_id, name="python", pinned=True)
    ignored = await TopicService().ignore(_FakeSession(), user_id=user_id, name="python", ignored=True)

    assert pinned.pinned is True
    assert ignored.ignored is True
    assert repository.received_pinned == (user_id, "python", True)
    assert repository.received_ignored == (user_id, "python", True)


def test_merge_topic_overrides_groups_aliases_and_hides_only_fully_ignored_groups() -> None:
    result = merge_topic_overrides(
        [
            TopicRecord(
                name="python",
                document_count=2,
                last_document_at=datetime(2026, 5, 1, tzinfo=UTC),
                source_names=("python",),
            ),
            TopicRecord(
                name="fastapi",
                document_count=1,
                last_document_at=datetime(2026, 5, 2, tzinfo=UTC),
                source_names=("fastapi",),
            ),
        ],
        [
            TopicOverrideRecord(source_name="python", display_name="Backend", pinned=True, ignored=False),
            TopicOverrideRecord(source_name="fastapi", display_name="Backend", pinned=False, ignored=True),
        ],
    )

    assert len(result) == 1
    assert result[0].name == "Backend"
    assert result[0].document_count == 3
    assert result[0].source_names == ("python", "fastapi")
    assert result[0].pinned is True
    assert result[0].ignored is False
