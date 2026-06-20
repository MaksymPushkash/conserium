from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

from src.conflicts import service as conflict_service_module
from src.conflicts.schemas import ConflictDetectionDTO
from src.conflicts.service import ConflictService, detect_conflicts, extract_conflict_claims
from src.documents.document_repository import DocumentRepository
from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.models.document import DocumentModel

if TYPE_CHECKING:
    from pytest import MonkeyPatch

    from src.kit.ports.ai.llm_service import ILLMService


class _FakeDocumentRepository:
    def __init__(self, documents: list[DocumentModel]) -> None:
        self.documents = documents
        self.received_collection_id: object | None = None
        self.received_status: object | None = None

    async def get_by_user_id(self, user_id: object, **kwargs: object) -> list[DocumentModel]:
        self.received_collection_id = kwargs.get("collection_id")
        self.received_status = kwargs.get("status")
        return self.documents


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


class _FakeSession:
    committed: bool = False

    async def flush(self) -> None:
        self.committed = True


class _Repositories:
    def __init__(self, documents: list[DocumentModel]) -> None:
        self.document_repo = _FakeDocumentRepository(documents)
        self.conflict_repo = _FakeConflictRepository()


class _RejectingLLMService:
    async def synthesize_answer(self, *, query: str, context: object) -> str:
        return "REJECTED"


def _document(title: str, raw_content: str, *, summary: str | None = None) -> DocumentModel:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    return DocumentModel(
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
async def test_detect_conflicts_loads_ready_documents(monkeypatch: MonkeyPatch) -> None:
    documents = [
        _document("Typing Guide", "Use type hints for public APIs."),
        _document("Prototype Notes", "Avoid type hints during quick spikes."),
    ]
    session, repositories = _wire_repositories(monkeypatch, documents)

    result = await ConflictService().detect(
        session,
        dto=ConflictDetectionDTO(user_id=uuid4(), limit=20),
        llm_service=None,
    )

    assert result.analyzed_document_count == 2
    assert result.conflicts[0].subject == "Typing"
    assert repositories.document_repo.received_status == DocumentStatus.READY
    assert repositories.conflict_repo.claim_count == 2
    assert repositories.conflict_repo.conflict_count == 1
    assert session.committed


@pytest.mark.asyncio
async def test_detect_conflicts_can_filter_with_llm_validation(monkeypatch: MonkeyPatch) -> None:
    documents = [
        _document("Typing Guide", "Use type hints for public APIs."),
        _document("Prototype Notes", "Avoid type hints during quick spikes."),
    ]
    session, repositories = _wire_repositories(monkeypatch, documents)

    result = await ConflictService().detect(
        session,
        dto=ConflictDetectionDTO(user_id=uuid4(), limit=20),
        llm_service=cast("ILLMService", _RejectingLLMService()),
    )

    assert result.conflicts == []
    assert repositories.conflict_repo.conflict_count == 0


def _wire_repositories(monkeypatch: MonkeyPatch, documents: list[DocumentModel]) -> tuple[_FakeSession, _Repositories]:
    repositories = _Repositories(documents)
    monkeypatch.setattr(DocumentRepository, "from_session", classmethod(lambda cls, session: repositories.document_repo))
    monkeypatch.setattr(conflict_service_module, "ConflictRepository", lambda session: repositories.conflict_repo)
    return _FakeSession(), repositories
