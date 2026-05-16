import uuid
from typing import TYPE_CHECKING, cast

from src.application.dtos.draft_dtos import DraftGenerateDTO
from src.application.dtos.query_dtos import QueryResultDTO, QuerySourceDTO
from src.application.dtos.refrag_dtos import RefragContextPackage
from src.application.use_cases.drafts.generate_draft_use_case import GenerateDraftUseCase, draft_gaps
from src.domain.exceptions import QueryValidationException
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.use_cases.query.query_use_case import QueryUseCase


class _FakeQueryUseCase:
    def __init__(self) -> None:
        self.received_query: str | None = None
        self.received_limit: int | None = None

    async def __call__(self, dto):
        self.received_query = dto.query
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


async def test_generate_draft_uses_existing_query_pipeline() -> None:
    fake_query_use_case = _FakeQueryUseCase()
    use_case = GenerateDraftUseCase(cast("QueryUseCase", fake_query_use_case))

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
    assert fake_query_use_case.received_limit == 6


async def test_generate_draft_rejects_empty_prompt() -> None:
    use_case = GenerateDraftUseCase(cast("QueryUseCase", _FakeQueryUseCase()))

    try:
        await use_case(DraftGenerateDTO(user_id=uuid.uuid4(), prompt=" "))
    except QueryValidationException as exc:
        assert str(exc) == "draft prompt cannot be empty"
    else:
        raise AssertionError("expected QueryValidationException")


def test_draft_gaps_detects_insufficient_context() -> None:
    assert draft_gaps("The provided context does not contain enough relevant information.") == [
        "Saved context is insufficient for this draft."
    ]
