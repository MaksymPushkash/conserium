from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.kit.exceptions import ResourceNotFoundException
from src.knowledge_gaps.service import KnowledgeGapService, document_matches_area, rubric_for_topic
from src.topics.repository import TopicDetailRecord, TopicDocumentRecord, TopicRecord, TopicRepository


class _FakeTopicRepository:
    def __init__(self, detail: TopicDetailRecord | None) -> None:
        self.detail = detail
        self.received_name: str | None = None
        self.received_document_limit: int | None = None

    async def get_detail_by_name(self, user_id: object, *, name: str, document_limit: int) -> TopicDetailRecord | None:
        self.received_name = name
        self.received_document_limit = document_limit
        return self.detail


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
async def test_knowledge_gaps_reports_covered_and_missing_areas(monkeypatch: pytest.MonkeyPatch) -> None:
    detail = _topic_detail(
        _topic_document("Python generators", "yield, iterator, and iterable examples"),
        _topic_document("Async Python", "asyncio concurrency notes"),
    )
    repository = _FakeTopicRepository(detail)
    monkeypatch.setattr(TopicRepository, "from_session", classmethod(lambda cls, session: repository))

    result = await KnowledgeGapService().get(object(), user_id=uuid4(), topic=" Python ", collection_id=None)

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
    assert repository.received_name == "Python"
    assert repository.received_document_limit == 200


@pytest.mark.asyncio
async def test_knowledge_gaps_requires_existing_topic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        TopicRepository,
        "from_session",
        classmethod(lambda cls, session: _FakeTopicRepository(None)),
    )

    with pytest.raises(ResourceNotFoundException, match="topic not found"):
        await KnowledgeGapService().get(object(), user_id=uuid4(), topic="Python", collection_id=None)
