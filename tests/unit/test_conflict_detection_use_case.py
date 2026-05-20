from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

from src.application.dtos.conflict_dtos import ConflictDetectionDTO
from src.application.use_cases.conflicts import DetectConflictsUseCase, detect_conflicts, extract_conflict_claims
from src.domain.entities.document_entity import DocumentEntity
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.ai.llm_service import ILLMService
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class _FakeDocumentRepository:
    def __init__(self, documents: list[DocumentEntity]) -> None:
        self.documents = documents
        self.received_collection_id: object | None = None
        self.received_status: object | None = None

    async def get_by_user_id(self, user_id: object, **kwargs: object) -> list[DocumentEntity]:
        self.received_collection_id = kwargs.get("collection_id")
        self.received_status = kwargs.get("status")
        return self.documents


class _FakeCollectionRepository:
    async def get_by_id(self, collection_id: object) -> object | None:
        return None


class _FakeConflictRepository:
    def __init__(self) -> None:
        self.claim_count = 0
        self.conflict_count = 0
        self.received_document_ids: list[object] = []

    async def replace_claims_for_documents(self, **kwargs: object) -> None:
        self.received_document_ids = cast("list[object]", kwargs["document_ids"])
        self.claim_count = len(cast("list[object]", kwargs["claims"]))

    async def replace_conflicts(self, **kwargs: object) -> None:
        self.conflict_count = len(cast("list[object]", kwargs["conflicts"]))


class _FakeUnitOfWork:
    def __init__(self, documents: list[DocumentEntity]) -> None:
        self.document_repo = _FakeDocumentRepository(documents)
        self.collection_repo = _FakeCollectionRepository()
        self.conflict_repo = _FakeConflictRepository()
        self.committed = False

    async def __aenter__(self) -> _FakeUnitOfWork:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


class _RejectingLLMService:
    async def synthesize_answer(self, *, query: str, context: object) -> str:
        return "REJECTED"


def _document(title: str, raw_content: str, *, summary: str | None = None) -> DocumentEntity:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    return DocumentEntity(
        id=uuid4(),
        user_id=uuid4(),
        collection_id=None,
        title=title,
        type=DocumentType.TEXT,
        status=DocumentStatus.READY,
        source_url=None,
        file_path=None,
        file_size_bytes=None,
        raw_content=raw_content,
        summary=summary,
        word_count=len(raw_content.split()),
        language="en",
        entities=None,
        categories=None,
        visual_metadata=None,
        suggested_questions=[],
        tags=[],
        doc_embedding=None,
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=now,
        updated_at=None,
    )


def test_detect_conflicts_finds_opposing_guidance() -> None:
    claims = extract_conflict_claims(
        [
            _document("ORM Guide", "Use ORM for application queries. It keeps code maintainable."),
            _document("Performance Notes", "Prefer raw SQL for performance critical paths."),
        ]
    )

    conflicts = detect_conflicts(claims)

    assert len(conflicts) == 1
    assert conflicts[0].subject == "ORM usage"
    assert len(conflicts[0].documents) == 2


def test_detect_conflicts_returns_empty_for_one_sided_guidance() -> None:
    claims = extract_conflict_claims(
        [
            _document("Testing Guide", "Use pytest and keep test coverage high."),
            _document("More Testing", "Write tests around domain behavior."),
        ]
    )

    assert detect_conflicts(claims) == []


@pytest.mark.asyncio
async def test_detect_conflicts_use_case_loads_ready_documents() -> None:
    documents = [
        _document("Typing Guide", "Use type hints for public APIs."),
        _document("Prototype Notes", "Avoid type hints during quick spikes."),
    ]
    uow = _FakeUnitOfWork(documents)
    use_case = DetectConflictsUseCase(cast("IUnitOfWork", uow))

    result = await use_case(ConflictDetectionDTO(user_id=uuid4(), limit=20))

    assert result.analyzed_document_count == 2
    assert result.conflicts[0].subject == "Typing"
    assert uow.document_repo.received_status == DocumentStatus.READY
    assert uow.conflict_repo.claim_count == 2
    assert uow.conflict_repo.conflict_count == 1
    assert uow.committed


@pytest.mark.asyncio
async def test_detect_conflicts_use_case_can_filter_with_llm_validation() -> None:
    documents = [
        _document("Typing Guide", "Use type hints for public APIs."),
        _document("Prototype Notes", "Avoid type hints during quick spikes."),
    ]
    uow = _FakeUnitOfWork(documents)
    use_case = DetectConflictsUseCase(cast("IUnitOfWork", uow), cast("ILLMService", _RejectingLLMService()))

    result = await use_case(ConflictDetectionDTO(user_id=uuid4(), limit=20))

    assert result.conflicts == []
    assert uow.conflict_repo.conflict_count == 0
