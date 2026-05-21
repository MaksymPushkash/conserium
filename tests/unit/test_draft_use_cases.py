import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from src.application.dtos.draft_dtos import DraftGenerateDTO
from src.application.dtos.query_dtos import QueryResultDTO, QuerySourceDTO
from src.application.dtos.refrag_dtos import RefragContextPackage
from src.application.use_cases.drafts.generate_draft_use_case import GenerateDraftUseCase, has_sufficient_draft_context
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import QueryValidationException
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.ai.llm_service import ILLMService
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.application.use_cases.query.query_use_case import QueryUseCase


class _FakeUnitOfWork:
    def __init__(self, documents: list[DocumentEntity] | None = None) -> None:
        self.document_repo = _FakeDocumentRepository(documents or [])

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _FakeLLMService:
    async def synthesize_answer(self, *, query: str, context: RefragContextPackage) -> str:
        return "# Fallback draft"


class _FakeDocumentRepository:
    def __init__(self, documents: list[DocumentEntity]) -> None:
        self.documents = documents

    async def get_by_user_id(self, *args: object, **kwargs: object) -> list[DocumentEntity]:
        return self.documents


class _FakeQueryUseCase:
    def __init__(self) -> None:
        self.received_query: str | None = None
        self.received_retrieval_query: str | None = None
        self.received_relevance_query: str | None = None
        self.received_limit: int | None = None

    async def __call__(self, dto):
        self.received_query = dto.query
        self.received_retrieval_query = dto.retrieval_query
        self.received_relevance_query = dto.relevance_query
        self.received_limit = dto.limit
        source = QuerySourceDTO(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_title="Python Notes",
            content="Generators yield values lazily.",
            page_number=None,
            chunk_index=0,
            score=0.9,
            used_in_answer=True,
        )
        return QueryResultDTO(
            conversation_id=uuid.uuid4(),
            query=dto.query,
            answer="# Python generators\n\nGenerators yield values lazily [1].",
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


async def test_generate_draft_uses_existing_query_pipeline() -> None:
    fake_query_use_case = _FakeQueryUseCase()
    use_case = GenerateDraftUseCase(
        cast("QueryUseCase", fake_query_use_case),
        cast("IUnitOfWork", _FakeUnitOfWork()),
        cast("ILLMService", _FakeLLMService()),
    )

    result = await use_case(
        DraftGenerateDTO(
            user_id=uuid.uuid4(),
            prompt="Write about Python generators",
            document_types=(DocumentType.TEXT,),
            limit=6,
        )
    )

    assert result.markdown.startswith("# Python generators")
    assert result.sources[0].document_title == "Python Notes"
    assert result.gaps == []
    assert fake_query_use_case.received_query is not None
    assert "Write a Markdown draft" in fake_query_use_case.received_query
    assert "Python generators" in fake_query_use_case.received_query
    assert fake_query_use_case.received_retrieval_query == "Write about Python generators"
    assert fake_query_use_case.received_relevance_query == "Write about Python generators"
    assert fake_query_use_case.received_limit == 12


async def test_generate_draft_falls_back_to_document_content_when_query_abstains() -> None:
    document = _make_document()
    use_case = GenerateDraftUseCase(
        cast("QueryUseCase", _FakeInsufficientQueryUseCase()),
        cast("IUnitOfWork", _FakeUnitOfWork([document])),
        cast("ILLMService", _FakeLLMService()),
    )

    result = await use_case(DraftGenerateDTO(user_id=document.user_id, prompt="Write from saved docs"))

    assert result.markdown == "# Fallback draft"
    assert result.sources[0].document_id == document.id
    assert result.gaps == []


async def test_generate_draft_rejects_empty_prompt() -> None:
    use_case = GenerateDraftUseCase(
        cast("QueryUseCase", _FakeQueryUseCase()),
        cast("IUnitOfWork", _FakeUnitOfWork()),
        cast("ILLMService", _FakeLLMService()),
    )

    try:
        await use_case(DraftGenerateDTO(user_id=uuid.uuid4(), prompt=" "))
    except QueryValidationException as exc:
        assert str(exc) == "draft prompt cannot be empty"
    else:
        raise AssertionError("expected QueryValidationException")


def test_has_sufficient_draft_context_uses_sources_not_answer_text() -> None:
    assert has_sufficient_draft_context([]) is False


def _make_document() -> DocumentEntity:
    return DocumentEntity(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        collection_id=None,
        title="Saved context",
        type=DocumentType.TEXT,
        status=DocumentStatus.READY,
        source_url=None,
        file_path=None,
        file_size_bytes=None,
        raw_content="Direct fallback content for drafts.",
        summary="Direct fallback summary.",
        word_count=5,
        language="en",
        doc_embedding=None,
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=datetime.now(UTC),
        updated_at=None,
    )
