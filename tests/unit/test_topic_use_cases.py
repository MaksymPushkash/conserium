import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.application.ports.persistence.topic_repository import TopicDetailRecord, TopicDocumentRecord, TopicRecord
from src.application.services.topics.topic_builder import topic_names_from_tags
from src.application.use_cases.topics import GetTopicDetailUseCase, ListTopicsUseCase
from src.domain.exceptions import ResourceNotFoundException

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


class _FakeUnitOfWork:
    def __init__(self) -> None:
        self.topic_repo = _FakeTopicRepository()

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


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
