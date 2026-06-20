import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.compare import service as compare_service_module
from src.compare.schemas import (
    CompareDocumentsDTO,
    CompareResultDTO,
)
from src.compare.service import CompareService
from src.documents.chunk_repository import ChunkRepository
from src.documents.document_repository import DocumentRepository
from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.kit.exceptions import (
    DocumentAccessDeniedException,
    DocumentNotFoundException,
    QueryValidationException,
    ResourceNotFoundException,
)
from src.models.chunk import ChunkModel
from src.models.document import DocumentModel
from src.query.schemas import QueryResultDTO, QuerySourceDTO, RefragContextPackage

if TYPE_CHECKING:
    from pytest import MonkeyPatch

    from src.kit.ports.ai.llm_service import ILLMService
    from src.query.service import QueryExecutor


class _FakeLLMService:
    async def synthesize_answer(self, *, query: str, context: RefragContextPackage) -> str:
        return "## Direct comparison\n\nFallback comparison."


class _FakeDocumentRepository:
    def __init__(self, documents: list[DocumentModel]) -> None:
        self.documents = {document.id: document for document in documents}

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentModel | None:
        return self.documents.get(document_id)


class _FakeChunkRepository:
    async def get_by_document_id(self, document_id: uuid.UUID) -> list[ChunkModel]:
        return []


class _FakeSession:
    async def flush(self) -> None:
        return None


class _Repositories:
    def __init__(self, documents: list[DocumentModel]) -> None:
        self.document_repo = _FakeDocumentRepository(documents)
        self.chunk_repo = _FakeChunkRepository()
        self.compare_repo = _FakeCompareRepository()


class _FakeCompareRepository:
    def __init__(self) -> None:
        self.records: list[CompareResultDTO] = []

    async def create(self, result: CompareResultDTO) -> CompareResultDTO:
        self.records.append(result)
        return result

    async def get_by_id(self, comparison_id: uuid.UUID) -> CompareResultDTO | None:
        return next((record for record in self.records if record.id == comparison_id), None)

    async def list_by_user_id(
        self,
        *,
        user_id: uuid.UUID,
        collection_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[CompareResultDTO]:
        records = [
            record
            for record in self.records
            if record.user_id == user_id and (collection_id is None or record.collection_id == collection_id)
        ]
        return records[offset : offset + limit]

    async def count_by_user_id(
        self,
        *,
        user_id: uuid.UUID,
        collection_id: uuid.UUID | None = None,
    ) -> int:
        return len(
            [
                record
                for record in self.records
                if record.user_id == user_id and (collection_id is None or record.collection_id == collection_id)
            ]
        )

    async def delete(self, comparison_id: uuid.UUID) -> None:
        self.records = [record for record in self.records if record.id != comparison_id]


class _FakeQueryExecutor:
    def __init__(self) -> None:
        self.received_document_ids: tuple[uuid.UUID, ...] | None = None
        self.received_relevance_query: str | None = None

    async def __call__(self, dto):
        self.received_document_ids = dto.document_ids
        self.received_relevance_query = dto.relevance_query
        source = QuerySourceDTO(
            chunk_id=uuid.uuid4(),
            document_id=dto.document_ids[0],
            document_title="FastAPI Notes",
            content="FastAPI focuses on API development.",
            page_number=None,
            chunk_index=0,
            score=0.9,
            used_in_answer=True,
        )
        return QueryResultDTO(
            conversation_id=uuid.uuid4(),
            query=dto.query,
            answer="## Shared ideas\n\nBoth discuss Python web work [1].",
            sources=[source],
            refrag_context=RefragContextPackage(
                query=dto.query,
                full_text_chunks=[],
                compressed_chunks=[],
                discarded_chunks=[],
                total_original_tokens=0,
                total_context_tokens=0,
                compression_strategy="none",
            ),
            debug=None,
        )


class _FakeInsufficientQueryExecutor:
    async def __call__(self, dto):
        return QueryResultDTO(
            conversation_id=uuid.uuid4(),
            query=dto.query,
            answer="The provided context does not contain enough relevant information.",
            sources=[],
            refrag_context=RefragContextPackage(
                query=dto.query,
                full_text_chunks=[],
                compressed_chunks=[],
                discarded_chunks=[],
                total_original_tokens=0,
                total_context_tokens=0,
                compression_strategy="none",
            ),
            debug=None,
        )


async def test_compare_documents_scopes_query_to_selected_documents(monkeypatch: "MonkeyPatch") -> None:
    user_id = uuid.uuid4()
    left_document = _make_document(user_id=user_id, title="FastAPI Notes")
    right_document = _make_document(user_id=user_id, title="Django Notes")
    query_executor = _FakeQueryExecutor()
    session, _ = _wire_repositories(monkeypatch, [left_document, right_document])

    result = await CompareService().compare_documents(
        session,
        query_executor=cast("QueryExecutor", query_executor),
        llm_service=cast("ILLMService", _FakeLLMService()),
        dto=CompareDocumentsDTO(
            user_id=user_id,
            left_document_id=left_document.id,
            right_document_id=right_document.id,
            prompt="focus on API routing",
        ),
    )

    assert result.left_title == "FastAPI Notes"
    assert result.right_title == "Django Notes"
    assert result.markdown.startswith("## Shared ideas")
    assert {source.document_title for source in result.sources} == {"FastAPI Notes"}
    assert result.id is not None
    assert result.dimensions == ["claims", "assumptions", "architecture", "tradeoffs", "contradictions", "missing_details"]
    assert [row.dimension for row in result.evidence_rows] == result.dimensions
    assert result.evidence_rows[0].left_source_id == result.sources[0].chunk_id
    assert result.evidence_rows[0].left_citation == "[1]"
    assert result.evidence_rows[0].confidence == 0.0
    assert result.evidence_rows[0].rationale is not None
    assert result.evidence_rows[0].rationale.startswith("Inferred fallback")
    assert query_executor.received_document_ids == (left_document.id, right_document.id)
    assert query_executor.received_relevance_query == ""


async def test_compare_documents_falls_back_to_direct_document_content(monkeypatch: "MonkeyPatch") -> None:
    user_id = uuid.uuid4()
    left_document = _make_document(user_id=user_id, title="Left")
    right_document = _make_document(user_id=user_id, title="Right")
    session, _ = _wire_repositories(monkeypatch, [left_document, right_document])

    result = await CompareService().compare_documents(
        session,
        query_executor=cast("QueryExecutor", _FakeInsufficientQueryExecutor()),
        llm_service=cast("ILLMService", _FakeLLMService()),
        dto=CompareDocumentsDTO(
            user_id=user_id,
            left_document_id=left_document.id,
            right_document_id=right_document.id,
        ),
    )

    assert result.markdown.startswith("## Direct comparison")
    assert {source.document_title for source in result.sources} == {"Left", "Right"}


async def test_compare_documents_persists_shared_collection_and_requested_dimensions(monkeypatch: "MonkeyPatch") -> None:
    user_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    left_document = _make_document(user_id=user_id, title="Left", collection_id=collection_id)
    right_document = _make_document(user_id=user_id, title="Right", collection_id=collection_id)
    session, repositories = _wire_repositories(monkeypatch, [left_document, right_document])

    result = await CompareService().compare_documents(
        session,
        query_executor=cast("QueryExecutor", _FakeInsufficientQueryExecutor()),
        llm_service=cast("ILLMService", _FakeLLMService()),
        dto=CompareDocumentsDTO(
            user_id=user_id,
            left_document_id=left_document.id,
            right_document_id=right_document.id,
            dimensions=("claims", "tradeoffs"),
        ),
    )

    assert result.collection_id == collection_id
    assert result.dimensions == ["claims", "tradeoffs"]
    assert [record.id for record in repositories.compare_repo.records] == [result.id]


async def test_compare_result_history_enforces_owner(monkeypatch: "MonkeyPatch") -> None:
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    record = _compare_result(user_id=user_id)
    session, repositories = _wire_repositories(monkeypatch, [])
    repositories.compare_repo.records = [record]
    service = CompareService()

    listed = await service.list_results(session, user_id=user_id, collection_id=None, limit=20, offset=0)
    fetched = await service.get_result(
        session,
        user_id=user_id,
        comparison_id=record.id,
    )

    assert [item.id for item in listed.items] == [record.id]
    assert listed.total == 1
    assert fetched.id == record.id
    with pytest.raises(ResourceNotFoundException, match="comparison not found"):
        await service.get_result(session, user_id=other_user_id, comparison_id=record.id)
    await service.delete_result(session, user_id=user_id, comparison_id=record.id)
    assert repositories.compare_repo.records == []


async def test_compare_documents_rejects_same_document(monkeypatch: "MonkeyPatch") -> None:
    document_id = uuid.uuid4()
    session, _ = _wire_repositories(monkeypatch, [])

    with pytest.raises(QueryValidationException, match="choose two different documents"):
        await CompareService().compare_documents(
            session,
            query_executor=cast("QueryExecutor", _FakeQueryExecutor()),
            llm_service=cast("ILLMService", _FakeLLMService()),
            dto=CompareDocumentsDTO(
                user_id=uuid.uuid4(),
                left_document_id=document_id,
                right_document_id=document_id,
            ),
        )


async def test_compare_documents_requires_owned_documents(monkeypatch: "MonkeyPatch") -> None:
    user_id = uuid.uuid4()
    left_document = _make_document(user_id=user_id)
    right_document = _make_document(user_id=uuid.uuid4())
    session, _ = _wire_repositories(monkeypatch, [left_document, right_document])

    with pytest.raises(DocumentAccessDeniedException):
        await CompareService().compare_documents(
            session,
            query_executor=cast("QueryExecutor", _FakeQueryExecutor()),
            llm_service=cast("ILLMService", _FakeLLMService()),
            dto=CompareDocumentsDTO(
                user_id=user_id,
                left_document_id=left_document.id,
                right_document_id=right_document.id,
            ),
        )


async def test_compare_documents_raises_when_document_is_missing(monkeypatch: "MonkeyPatch") -> None:
    session, _ = _wire_repositories(monkeypatch, [])

    with pytest.raises(DocumentNotFoundException):
        await CompareService().compare_documents(
            session,
            query_executor=cast("QueryExecutor", _FakeQueryExecutor()),
            llm_service=cast("ILLMService", _FakeLLMService()),
            dto=CompareDocumentsDTO(
                user_id=uuid.uuid4(),
                left_document_id=uuid.uuid4(),
                right_document_id=uuid.uuid4(),
            ),
        )


def _wire_repositories(monkeypatch: "MonkeyPatch", documents: list[DocumentModel]) -> tuple[_FakeSession, _Repositories]:
    repositories = _Repositories(documents)
    monkeypatch.setattr(DocumentRepository, "from_session", classmethod(lambda cls, session: repositories.document_repo))
    monkeypatch.setattr(ChunkRepository, "from_session", classmethod(lambda cls, session: repositories.chunk_repo))
    monkeypatch.setattr(compare_service_module, "CompareRepository", lambda session: repositories.compare_repo)
    return _FakeSession(), repositories


def _make_document(
    *,
    user_id: uuid.UUID,
    title: str = "Saved document",
    collection_id: uuid.UUID | None = None,
) -> DocumentModel:
    return DocumentModel(
        id=uuid.uuid4(),
        user_id=user_id,
        collection_id=collection_id,
        title=title,
        type=DocumentType.TEXT,
        status=DocumentStatus.READY,
        source_url=None,
        file_path=None,
        file_size_bytes=None,
        raw_content="Important saved content.",
        summary="Important saved summary.",
        word_count=3,
        language="en",
        doc_embedding=None,
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=datetime.now(UTC),
        updated_at=None,
    )


def _compare_result(*, user_id: uuid.UUID) -> CompareResultDTO:
    left_document_id = uuid.uuid4()
    right_document_id = uuid.uuid4()
    return CompareResultDTO(
        id=uuid.uuid4(),
        user_id=user_id,
        collection_id=None,
        left_document_id=left_document_id,
        right_document_id=right_document_id,
        left_title="Left",
        right_title="Right",
        dimensions=["claims"],
        markdown="## Summary",
        summary="Left vs Right.",
        evidence_rows=[],
        sources=[],
        created_at=datetime.now(UTC),
    )
