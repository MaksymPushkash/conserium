from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

from src.application.ports.persistence.topic_repository import TopicDetailRecord, TopicDocumentRecord, TopicRecord
from src.application.use_cases.knowledge_gaps import GetKnowledgeGapsUseCase, document_matches_area, rubric_for_topic
from src.domain.exceptions import ResourceNotFoundException

if TYPE_CHECKING:
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class _FakeTopicRepository:
    def __init__(self, detail: TopicDetailRecord | None) -> None:
        self.detail = detail
        self.received_name: str | None = None
        self.received_document_limit: int | None = None

    async def get_detail_by_name(self, user_id: object, *, name: str, document_limit: int) -> TopicDetailRecord | None:
        self.received_name = name
        self.received_document_limit = document_limit
        return self.detail


class _FakeUnitOfWork:
    def __init__(self, detail: TopicDetailRecord | None) -> None:
        self.topic_repo = _FakeTopicRepository(detail)

    async def __aenter__(self) -> _FakeUnitOfWork:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def _topic_document(title: str, summary: str | None) -> TopicDocumentRecord:
    return TopicDocumentRecord(
        id=uuid4(),
        title=title,
        type="TEXT",
        status="READY",
        summary=summary,
        created_at=datetime(2026, 5, 17, tzinfo=UTC),
    )


def _topic_detail(*documents: TopicDocumentRecord, name: str = "Python") -> TopicDetailRecord:
    return TopicDetailRecord(
        topic=TopicRecord(name=name, document_count=len(documents), last_document_at=None),
        documents=list(documents),
    )


def test_rubric_for_topic_uses_specific_rubric() -> None:
    names = [area.name for area in rubric_for_topic("Advanced Python")]

    assert "Async and concurrency" in names
    assert "Typing" in names


def test_rubric_for_topic_uses_alias_rubrics() -> None:
    names = [area.name for area in rubric_for_topic("TypeScript frontend")]

    assert "Type system" in names
    assert "API boundaries" in names


def test_document_matches_area_from_title_or_summary() -> None:
    area = next(area for area in rubric_for_topic("Python") if area.name == "Typing")

    assert document_matches_area(_topic_document("Protocols in Python", "structural typing with mypy"), area)
    assert not document_matches_area(_topic_document("Decorators", "wrapping callables"), area)


@pytest.mark.asyncio
async def test_knowledge_gaps_reports_covered_and_missing_areas() -> None:
    detail = _topic_detail(
        _topic_document("Python generators", "yield, iterator, and iterable examples"),
        _topic_document("Async Python", "asyncio concurrency notes"),
    )
    uow = _FakeUnitOfWork(detail)
    use_case = GetKnowledgeGapsUseCase(cast("IUnitOfWork", uow))

    result = await use_case(user_id=uuid4(), topic=" Python ")

    assert result.topic == "Python"
    assert result.covered_count == 2
    assert result.missing_count == 5
    assert result.coverage_ratio == pytest.approx(2 / 7)
    assert result.why_detected == "5 rubric area(s) are missing; current coverage is 29%."
    assert result.missing_source_types == ["article", "example", "reference"]
    assert result.severity == "medium"
    missing_area = next(area for area in result.areas if area.name == "Testing")
    assert missing_area.id == "python--testing"
    assert missing_area.why_detected == "No saved source matched the Testing rubric keywords."
    assert missing_area.rationale == "Testing is missing from the current saved context and can weaken retrieval or synthesis."
    assert missing_area.suggested_actions[0] == "Add a reference source about Python Testing."
    assert uow.topic_repo.received_name == "Python"
    assert uow.topic_repo.received_document_limit == 200


@pytest.mark.asyncio
async def test_knowledge_gaps_requires_existing_topic() -> None:
    use_case = GetKnowledgeGapsUseCase(cast("IUnitOfWork", _FakeUnitOfWork(None)))

    with pytest.raises(ResourceNotFoundException, match="topic not found"):
        await use_case(user_id=uuid4(), topic="Python")
