import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.application.ports.persistence.topic_repository import (
    TopicDetailRecord,
    TopicDocumentRecord,
    TopicOverrideEventRecord,
    TopicOverrideRecord,
    TopicRecord,
)
from src.application.services.topics.topic_builder import topic_names_from_tags
from src.application.use_cases.topics import (
    GetTopicDetailUseCase,
    IgnoreTopicUseCase,
    ListTopicsUseCase,
    MergeTopicsUseCase,
    PinTopicUseCase,
    RenameTopicUseCase,
)
from src.domain.exceptions import ResourceNotFoundException
from src.infrastructure.database.repositories.topic_repository import merge_topic_overrides

if TYPE_CHECKING:
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


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


class _FakeUnitOfWork:
    def __init__(self) -> None:
        self.topic_repo = _FakeTopicRepository()
        self.committed = False

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


async def test_list_topics_returns_paginated_topic_groups() -> None:
    use_case = ListTopicsUseCase(cast("IUnitOfWork", _FakeUnitOfWork()))

    result = await use_case(user_id=uuid.uuid4(), limit=1, offset=0)

    assert result.total == 2
    assert result.limit == 1
    assert result.offset == 0
    assert result.items[0].name == "python"
    assert result.items[0].document_count == 3


async def test_get_topic_detail_returns_representative_documents() -> None:
    uow = _FakeUnitOfWork()
    use_case = GetTopicDetailUseCase(cast("IUnitOfWork", uow))
    user_id = uuid.uuid4()

    result = await use_case(user_id=user_id, name=" Python ", document_limit=5)

    assert result.topic.name == "python"
    assert result.documents[0].title == "Python Async"
    assert uow.topic_repo.received_detail == (user_id, "python", 5)
    assert uow.topic_repo.received_events == (user_id, "python", 10)


async def test_get_topic_detail_raises_when_topic_is_missing() -> None:
    uow = _FakeUnitOfWork()
    uow.topic_repo.detail = None
    use_case = GetTopicDetailUseCase(cast("IUnitOfWork", uow))

    with pytest.raises(ResourceNotFoundException):
        await use_case(user_id=uuid.uuid4(), name="missing")


def test_topic_names_from_tags_limits_topic_count() -> None:
    tags = [f"tag-{index}" for index in range(10)]

    result = topic_names_from_tags(tags)

    assert result == tags[:8]


async def test_rename_topic_persists_display_override() -> None:
    uow = _FakeUnitOfWork()
    user_id = uuid.uuid4()
    result = await RenameTopicUseCase(cast("IUnitOfWork", uow))(user_id=user_id, name=" Python ", display_name="Backend")

    assert result.name == "Backend"
    assert result.source_names == ("Python",)
    assert uow.topic_repo.received_rename == (user_id, "Python", "Backend")
    assert uow.committed


async def test_merge_topics_persists_source_aliases() -> None:
    uow = _FakeUnitOfWork()
    user_id = uuid.uuid4()
    result = await MergeTopicsUseCase(cast("IUnitOfWork", uow))(user_id=user_id, name="Backend", source_names=["python", "fastapi"])

    assert result.name == "Backend"
    assert result.source_names == ("python", "fastapi", "Backend")
    assert uow.topic_repo.received_merge == (user_id, ["python", "fastapi", "Backend"], "Backend")
    assert uow.committed


async def test_pin_and_ignore_topics_persist_flags() -> None:
    uow = _FakeUnitOfWork()
    user_id = uuid.uuid4()

    pinned = await PinTopicUseCase(cast("IUnitOfWork", uow))(user_id=user_id, name="python", pinned=True)
    ignored = await IgnoreTopicUseCase(cast("IUnitOfWork", uow))(user_id=user_id, name="python", ignored=True)

    assert pinned.pinned is True
    assert ignored.ignored is True
    assert uow.topic_repo.received_pinned == (user_id, "python", True)
    assert uow.topic_repo.received_ignored == (user_id, "python", True)


def test_merge_topic_overrides_groups_aliases_and_hides_only_fully_ignored_groups() -> None:
    result = merge_topic_overrides(
        [
            TopicRecord(name="python", document_count=2, last_document_at=datetime(2026, 5, 1, tzinfo=UTC), source_names=("python",)),
            TopicRecord(name="fastapi", document_count=1, last_document_at=datetime(2026, 5, 2, tzinfo=UTC), source_names=("fastapi",)),
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
