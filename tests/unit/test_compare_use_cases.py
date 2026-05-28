import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.application.dtos.compare_dtos import (
    CompareDocumentsDTO,
    CompareResultDTO,
    DeleteCompareResultDTO,
    GetCompareResultDTO,
    ListCompareResultsDTO,
)
from src.application.dtos.query_dtos import QueryResultDTO, QuerySourceDTO
from src.application.dtos.refrag_dtos import RefragContextPackage
from src.application.use_cases.compare import (
    CompareDocumentsUseCase,
    DeleteCompareResultUseCase,
    GetCompareResultUseCase,
    ListCompareResultsUseCase,
)
from src.domain.entities.chunk_entity import ChunkEntity
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import (
    DocumentAccessDeniedException,
    DocumentNotFoundException,
    QueryValidationException,
    ResourceNotFoundException,
)
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.ai.llm_service import ILLMService
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.application.use_cases.query.query_use_case import QueryUseCase


class _FakeLLMService:
    async def synthesize_answer(self, *, query: str, context: RefragContextPackage) -> str:
        return "## Direct comparison\n\nFallback comparison."


class _FakeDocumentRepository:
    def __init__(self, documents: list[DocumentEntity]) -> None:
        self.documents = {document.id: document for document in documents}

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentEntity | None:
        return self.documents.get(document_id)


class _FakeChunkRepository:
    async def get_by_document_id(self, document_id: uuid.UUID) -> list[ChunkEntity]:
        return []


class _FakeUnitOfWork:
    def __init__(self, documents: list[DocumentEntity]) -> None:
        self.document_repo = _FakeDocumentRepository(documents)
        self.chunk_repo = _FakeChunkRepository()
        self.compare_repo = _FakeCompareRepository()

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def commit(self) -> None:
        return None


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


class _FakeQueryUseCase:
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


class _FakeInsufficientQueryUseCase:
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


async def test_compare_documents_scopes_query_to_selected_documents() -> None:
    user_id = uuid.uuid4()
    left_document = _make_document(user_id=user_id, title="FastAPI Notes")
    right_document = _make_document(user_id=user_id, title="Django Notes")
    query_use_case = _FakeQueryUseCase()
    use_case = CompareDocumentsUseCase(
        cast("QueryUseCase", query_use_case),
        cast("IUnitOfWork", _FakeUnitOfWork([left_document, right_document])),
        cast("ILLMService", _FakeLLMService()),
    )

    result = await use_case(
        CompareDocumentsDTO(
            user_id=user_id,
            left_document_id=left_document.id,
            right_document_id=right_document.id,
            prompt="focus on API routing",
        )
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
    assert query_use_case.received_document_ids == (left_document.id, right_document.id)
    assert query_use_case.received_relevance_query == ""


async def test_compare_documents_falls_back_to_direct_document_content() -> None:
    user_id = uuid.uuid4()
    left_document = _make_document(user_id=user_id, title="Left")
    right_document = _make_document(user_id=user_id, title="Right")
    use_case = CompareDocumentsUseCase(
        cast("QueryUseCase", _FakeInsufficientQueryUseCase()),
        cast("IUnitOfWork", _FakeUnitOfWork([left_document, right_document])),
        cast("ILLMService", _FakeLLMService()),
    )

    result = await use_case(
        CompareDocumentsDTO(
            user_id=user_id,
            left_document_id=left_document.id,
            right_document_id=right_document.id,
        )
    )

    assert result.markdown.startswith("## Direct comparison")
    assert {source.document_title for source in result.sources} == {"Left", "Right"}


async def test_compare_documents_persists_shared_collection_and_requested_dimensions() -> None:
    user_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    left_document = _make_document(user_id=user_id, title="Left", collection_id=collection_id)
    right_document = _make_document(user_id=user_id, title="Right", collection_id=collection_id)
    uow = _FakeUnitOfWork([left_document, right_document])
    use_case = CompareDocumentsUseCase(
        cast("QueryUseCase", _FakeInsufficientQueryUseCase()),
        cast("IUnitOfWork", uow),
        cast("ILLMService", _FakeLLMService()),
    )

    result = await use_case(
        CompareDocumentsDTO(
            user_id=user_id,
            left_document_id=left_document.id,
            right_document_id=right_document.id,
            dimensions=("claims", "tradeoffs"),
        )
    )

    assert result.collection_id == collection_id
    assert result.dimensions == ["claims", "tradeoffs"]
    assert uow.compare_repo.records == [result]


async def test_compare_result_history_use_cases_enforce_owner() -> None:
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    record = _compare_result(user_id=user_id)
    uow = _FakeUnitOfWork([])
    uow.compare_repo.records = [record]

    listed = await ListCompareResultsUseCase(cast("IUnitOfWork", uow))(ListCompareResultsDTO(user_id=user_id))
    fetched = await GetCompareResultUseCase(cast("IUnitOfWork", uow))(
        GetCompareResultDTO(user_id=user_id, comparison_id=record.id)
    )

    assert listed.items == [record]
    assert listed.total == 1
    assert fetched == record
    with pytest.raises(ResourceNotFoundException, match="comparison not found"):
        await GetCompareResultUseCase(cast("IUnitOfWork", uow))(
            GetCompareResultDTO(user_id=other_user_id, comparison_id=record.id)
        )
    await DeleteCompareResultUseCase(cast("IUnitOfWork", uow))(
        DeleteCompareResultDTO(user_id=user_id, comparison_id=record.id)
    )
    assert uow.compare_repo.records == []


async def test_compare_documents_rejects_same_document() -> None:
    document_id = uuid.uuid4()
    use_case = CompareDocumentsUseCase(
        cast("QueryUseCase", _FakeQueryUseCase()),
        cast("IUnitOfWork", _FakeUnitOfWork([])),
        cast("ILLMService", _FakeLLMService()),
    )

    with pytest.raises(QueryValidationException, match="choose two different documents"):
        await use_case(
            CompareDocumentsDTO(
                user_id=uuid.uuid4(),
                left_document_id=document_id,
                right_document_id=document_id,
            )
        )


async def test_compare_documents_requires_owned_documents() -> None:
    user_id = uuid.uuid4()
    left_document = _make_document(user_id=user_id)
    right_document = _make_document(user_id=uuid.uuid4())
    use_case = CompareDocumentsUseCase(
        cast("QueryUseCase", _FakeQueryUseCase()),
        cast("IUnitOfWork", _FakeUnitOfWork([left_document, right_document])),
        cast("ILLMService", _FakeLLMService()),
    )

    with pytest.raises(DocumentAccessDeniedException):
        await use_case(
            CompareDocumentsDTO(
                user_id=user_id,
                left_document_id=left_document.id,
                right_document_id=right_document.id,
            )
        )


async def test_compare_documents_raises_when_document_is_missing() -> None:
    use_case = CompareDocumentsUseCase(
        cast("QueryUseCase", _FakeQueryUseCase()),
        cast("IUnitOfWork", _FakeUnitOfWork([])),
        cast("ILLMService", _FakeLLMService()),
    )

    with pytest.raises(DocumentNotFoundException):
        await use_case(
            CompareDocumentsDTO(
                user_id=uuid.uuid4(),
                left_document_id=uuid.uuid4(),
                right_document_id=uuid.uuid4(),
            )
        )


def _make_document(
    *,
    user_id: uuid.UUID,
    title: str = "Saved document",
    collection_id: uuid.UUID | None = None,
) -> DocumentEntity:
    return DocumentEntity(
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
