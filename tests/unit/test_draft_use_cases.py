import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from src.application.dtos.draft_dtos import DraftGenerateDTO
from src.application.dtos.query_dtos import QueryResultDTO, QuerySourceDTO
from src.application.dtos.refrag_dtos import RefragContextPackage
from src.application.ports.persistence.draft_repository import DraftRecord, DraftVersionRecord
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
        self.draft_repo = _FakeDraftRepository()
        self.committed = False

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


class _FakeLLMService:
    async def synthesize_answer(self, *, query: str, context: RefragContextPackage) -> str:
        return "# Fallback draft"


class _FakeDocumentRepository:
    def __init__(self, documents: list[DocumentEntity]) -> None:
        self.documents = documents

    async def get_by_user_id(self, *args: object, **kwargs: object) -> list[DocumentEntity]:
        return self.documents

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentEntity | None:
        return next((document for document in self.documents if document.id == document_id), None)


class _FakeDraftRepository:
    def __init__(self) -> None:
        self.records: dict[uuid.UUID, DraftRecord] = {}
        self.versions: dict[uuid.UUID, list[DraftVersionRecord]] = {}

    async def create_with_version(self, *, draft: DraftRecord, version: DraftVersionRecord) -> DraftRecord:
        saved = _saved_draft(draft, version)
        self.records[saved.id] = saved
        self.versions[saved.id] = [_saved_version(version)]
        return saved

    async def append_version(self, *, draft_id: uuid.UUID, version: DraftVersionRecord) -> DraftRecord:
        saved = _saved_draft(self.records[draft_id], version)
        self.records[draft_id] = saved
        self.versions.setdefault(draft_id, []).append(_saved_version(version))
        return saved

    async def get_by_id(self, draft_id: uuid.UUID) -> DraftRecord | None:
        return self.records.get(draft_id)


class _FakeQueryUseCase:
    def __init__(self) -> None:
        self.received_query: str | None = None
        self.received_retrieval_query: str | None = None
        self.received_relevance_query: str | None = None
        self.received_limit: int | None = None
        self.received_document_ids: tuple[uuid.UUID, ...] | None = None
        self.received_tag_names: tuple[str, ...] | None = None

    async def __call__(self, dto):
        self.received_query = dto.query
        self.received_retrieval_query = dto.retrieval_query
        self.received_relevance_query = dto.relevance_query
        self.received_limit = dto.limit
        self.received_document_ids = dto.document_ids
        self.received_tag_names = dto.tag_names
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
    def __init__(self, *, include_unused_source: bool = False) -> None:
        self._include_unused_source = include_unused_source

    async def __call__(self, dto):
        sources = []
        if self._include_unused_source:
            sources.append(
                QuerySourceDTO(
                    chunk_id=uuid.uuid4(),
                    document_id=uuid.uuid4(),
                    document_title="Weak match",
                    content="Weakly related context.",
                    page_number=None,
                    chunk_index=0,
                    score=0.1,
                    used_in_answer=False,
                )
            )
        return QueryResultDTO(
            conversation_id=uuid.uuid4(),
            query=dto.query,
            answer="The provided context does not contain enough relevant information.",
            sources=sources,
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
    assert result.draft_id
    assert result.version_id
    assert result.version_number == 1
    assert result.template_id == "brief"
    assert result.scope_type == "all"
    assert result.sources[0].document_title == "Python Notes"
    assert result.gaps == []
    assert fake_query_use_case.received_query is not None
    assert "Write a Markdown draft" in fake_query_use_case.received_query
    assert "Python generators" in fake_query_use_case.received_query
    assert fake_query_use_case.received_retrieval_query == "Write about Python generators"
    assert fake_query_use_case.received_relevance_query == "Write about Python generators"
    assert fake_query_use_case.received_limit == 12


async def test_generate_draft_uses_explicit_document_scope() -> None:
    document = _make_document()
    fake_query_use_case = _FakeQueryUseCase()
    use_case = GenerateDraftUseCase(
        cast("QueryUseCase", fake_query_use_case),
        cast("IUnitOfWork", _FakeUnitOfWork([document])),
        cast("ILLMService", _FakeLLMService()),
    )

    await use_case(
        DraftGenerateDTO(
            user_id=document.user_id,
            prompt="Write from selected docs",
            document_ids=(document.id,),
        )
    )

    assert fake_query_use_case.received_document_ids == (document.id,)


async def test_generate_draft_uses_topic_as_tag_scope() -> None:
    fake_query_use_case = _FakeQueryUseCase()
    use_case = GenerateDraftUseCase(
        cast("QueryUseCase", fake_query_use_case),
        cast("IUnitOfWork", _FakeUnitOfWork()),
        cast("ILLMService", _FakeLLMService()),
    )

    await use_case(DraftGenerateDTO(user_id=uuid.uuid4(), prompt="Write about cloud", topic="Cloud"))

    assert fake_query_use_case.received_tag_names == ("cloud",)


async def test_generate_draft_appends_version_for_existing_draft() -> None:
    fake_query_use_case = _FakeQueryUseCase()
    uow = _FakeUnitOfWork()
    existing = _existing_draft(user_id=uuid.uuid4())
    uow.draft_repo.records[existing.id] = existing
    use_case = GenerateDraftUseCase(
        cast("QueryUseCase", fake_query_use_case),
        cast("IUnitOfWork", uow),
        cast("ILLMService", _FakeLLMService()),
    )

    result = await use_case(DraftGenerateDTO(user_id=existing.user_id, draft_id=existing.id, prompt="Regenerate"))

    assert result.draft_id == existing.id
    assert result.version_number == 2


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


async def test_generate_draft_falls_back_when_sources_are_not_used_in_answer() -> None:
    document = _make_document()
    use_case = GenerateDraftUseCase(
        cast("QueryUseCase", _FakeInsufficientQueryUseCase(include_unused_source=True)),
        cast("IUnitOfWork", _FakeUnitOfWork([document])),
        cast("ILLMService", _FakeLLMService()),
    )

    result = await use_case(DraftGenerateDTO(user_id=document.user_id, prompt="Write from saved docs"))

    assert result.markdown == "# Fallback draft"
    assert result.sources[0].document_id == document.id


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


def _existing_draft(*, user_id: uuid.UUID) -> DraftRecord:
    draft_id = uuid.uuid4()
    version_id = uuid.uuid4()
    return DraftRecord(
        id=draft_id,
        user_id=user_id,
        collection_id=None,
        title="Brief: Old",
        prompt="Old",
        template_id="brief",
        scope_type="all",
        topic=None,
        knowledge_gap_id=None,
        scope_metadata={},
        markdown="# Old",
        sources=[],
        gaps=[],
        current_version_id=version_id,
        version_number=1,
        created_at=datetime.now(UTC),
        updated_at=None,
    )


def _saved_draft(draft: DraftRecord, version: DraftVersionRecord) -> DraftRecord:
    return DraftRecord(
        id=draft.id,
        user_id=draft.user_id,
        collection_id=version.collection_id,
        title=version.title,
        prompt=version.prompt,
        template_id=version.template_id,
        scope_type=version.scope_type,
        topic=version.topic,
        knowledge_gap_id=version.knowledge_gap_id,
        scope_metadata=version.scope_metadata,
        markdown=version.markdown,
        sources=version.sources,
        gaps=version.gaps,
        current_version_id=version.id,
        version_number=version.version_number,
        created_at=draft.created_at or datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _saved_version(version: DraftVersionRecord) -> DraftVersionRecord:
    return DraftVersionRecord(
        id=version.id,
        draft_id=version.draft_id,
        user_id=version.user_id,
        version_number=version.version_number,
        title=version.title,
        prompt=version.prompt,
        template_id=version.template_id,
        scope_type=version.scope_type,
        collection_id=version.collection_id,
        topic=version.topic,
        knowledge_gap_id=version.knowledge_gap_id,
        scope_metadata=version.scope_metadata,
        markdown=version.markdown,
        sources=version.sources,
        gaps=version.gaps,
        created_at=datetime.now(UTC),
    )
