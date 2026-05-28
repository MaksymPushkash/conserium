import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from src.application.agents.query.conversation_context_agent import ConversationContextAgent
from src.application.agents.query.retrieval_agent import RetrievalAgent
from src.application.agents.query.router_agent import RouterAgent
from src.application.agents.query.state import ConseriumQueryState, QueryType
from src.application.agents.query.synthesis_agent import ABSTENTION_ANSWER, SynthesisAgent
from src.application.dtos.conversation_dtos import ConversationSourceDTO, ConversationTurnDTO
from src.application.dtos.query_dtos import QuerySourceDTO
from src.application.dtos.refrag_dtos import RefragChunk, RefragContextPackage, RefragRepresentation
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.ai.llm_service import ILLMService
    from src.application.services.retrieval.hybrid_retrieval_service import HybridRetrievalService


def test_router_agent_marks_summary_queries() -> None:
    state = ConseriumQueryState(
        query="Summarize my notes about startup development",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
    )

    routed_state = RouterAgent().route(state)

    assert routed_state.query_type == QueryType.SUMMARY


def test_router_agent_defaults_to_search() -> None:
    state = ConseriumQueryState(
        query="What did I read about Clean Architecture?",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
    )

    routed_state = RouterAgent().route(state)

    assert routed_state.query_type == QueryType.SEARCH


def test_router_agent_uses_word_boundaries_for_summary_markers() -> None:
    state = ConseriumQueryState(
        query="Find documents about summary_stats tables",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
    )

    routed_state = RouterAgent().route(state)

    assert routed_state.query_type == QueryType.SEARCH


def test_router_agent_uses_word_boundaries_for_ukrainian_summary_markers() -> None:
    state = ConseriumQueryState(
        query="Знайди нотатку про підсумуймо результати",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
    )

    routed_state = RouterAgent().route(state)

    assert routed_state.query_type == QueryType.SEARCH


def test_router_agent_marks_document_qa_queries() -> None:
    state = ConseriumQueryState(
        query="What does this document say about tests?",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
    )

    routed_state = RouterAgent().route(state)

    assert routed_state.query_type == QueryType.DOCUMENT_QA


def test_router_agent_does_not_match_pdf_inside_another_token() -> None:
    state = ConseriumQueryState(
        query="Find notes about pdfium rendering",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
    )

    routed_state = RouterAgent().route(state)

    assert routed_state.query_type == QueryType.SEARCH


def test_conversation_context_agent_rewrites_follow_up_query_and_promotes_sources() -> None:
    document_id = uuid.uuid4()
    state = ConseriumQueryState(
        query="What about testing?",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
        conversation_turns=[
            ConversationTurnDTO(
                query="What did I read about Clean Architecture?",
                answer="You read that dependencies should point inward.",
                sources=[
                    ConversationSourceDTO(
                        chunk_id=uuid.uuid4(),
                        document_id=document_id,
                        document_title="Architecture Notes",
                        page_number=3,
                        chunk_index=0,
                        score=0.8,
                    )
                ],
                created_at=datetime.now(UTC),
            )
        ],
    )

    result = ConversationContextAgent().apply(state)

    assert result.retrieval_query is not None
    assert "Current follow-up question: What about testing?" in result.retrieval_query
    assert "Previous question: What did I read about Clean Architecture?" in result.retrieval_query
    assert result.promoted_document_ids == [document_id]


def test_conversation_context_agent_keeps_standalone_query_unchanged() -> None:
    state = ConseriumQueryState(
        query="Explain PostgreSQL pgvector indexing for saved PDFs",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
        conversation_turns=[
            ConversationTurnDTO(
                query="Unrelated previous question",
                answer="Unrelated previous answer",
                sources=[],
                created_at=datetime.now(UTC),
            )
        ],
    )

    result = ConversationContextAgent().apply(state)

    assert result.retrieval_query == state.query
    assert result.promoted_document_ids == []


def test_conversation_context_agent_preserves_explicit_retrieval_query() -> None:
    state = ConseriumQueryState(
        query="Write a Markdown draft using only saved context about Python generators",
        retrieval_query="Python generators",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
        conversation_turns=[
            ConversationTurnDTO(
                query="Previous question",
                answer="Previous answer",
                sources=[],
                created_at=datetime.now(UTC),
            )
        ],
    )

    result = ConversationContextAgent().apply(state)

    assert result.retrieval_query == "Python generators"
    assert result.promoted_document_ids == []


def test_conversation_context_agent_does_not_rewrite_short_standalone_query() -> None:
    previous_document_id = uuid.uuid4()
    state = ConseriumQueryState(
        query="PostgreSQL indexes",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
        conversation_turns=[
            ConversationTurnDTO(
                query="What did I read about Clean Architecture?",
                answer="You read that dependencies should point inward.",
                sources=[
                    ConversationSourceDTO(
                        chunk_id=uuid.uuid4(),
                        document_id=previous_document_id,
                        document_title="Architecture Notes",
                        page_number=None,
                        chunk_index=0,
                        score=0.7,
                    )
                ],
                created_at=datetime.now(UTC),
            )
        ],
    )

    result = ConversationContextAgent().apply(state)

    assert result.retrieval_query == "PostgreSQL indexes"
    assert result.promoted_document_ids == []


def test_conversation_context_agent_does_not_treat_connective_search_as_follow_up() -> None:
    previous_document_id = uuid.uuid4()
    state = ConseriumQueryState(
        query="PostgreSQL and pgvector",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
        conversation_turns=[
            ConversationTurnDTO(
                query="What did I read about Clean Architecture?",
                answer="You read that dependencies should point inward.",
                sources=[
                    ConversationSourceDTO(
                        chunk_id=uuid.uuid4(),
                        document_id=previous_document_id,
                        document_title="Architecture Notes",
                        page_number=None,
                        chunk_index=0,
                        score=0.7,
                    )
                ],
                created_at=datetime.now(UTC),
            )
        ],
    )

    result = ConversationContextAgent().apply(state)

    assert result.retrieval_query == "PostgreSQL and pgvector"
    assert result.promoted_document_ids == []


class _FakeRetrievalService:
    def __init__(self) -> None:
        self.received_query: str | None = None
        self.received_tag_names: tuple[str, ...] | None = None
        self.received_document_types: tuple[DocumentType, ...] | None = None
        self.received_document_ids: tuple[uuid.UUID, ...] | None = None

    async def retrieve(
        self,
        *,
        query: str,
        user_id: uuid.UUID,
        limit: int,
        collection_id: uuid.UUID | None,
        tag_names: tuple[str, ...] | None = None,
        document_types: tuple[DocumentType, ...] | None = None,
        document_ids: tuple[uuid.UUID, ...] | None = None,
    ) -> list[QuerySourceDTO]:
        self.received_query = query
        self.received_tag_names = tag_names
        self.received_document_types = document_types
        self.received_document_ids = document_ids
        promoted_document_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        other_document_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
        return [
            QuerySourceDTO(
                chunk_id=uuid.uuid4(),
                document_id=other_document_id,
                document_title="Other",
                content="Other document content about unrelated deployment notes.",
                page_number=None,
                chunk_index=0,
                score=0.9,
            ),
            QuerySourceDTO(
                chunk_id=uuid.uuid4(),
                document_id=promoted_document_id,
                document_title="Previous Source",
                content="Previous source content about regression tests and query context.",
                page_number=None,
                chunk_index=1,
                score=0.5,
            ),
        ]


async def test_retrieval_agent_uses_contextual_query_and_promotes_previous_documents() -> None:
    promoted_document_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    state = ConseriumQueryState(
        query="What about tests?",
        retrieval_query="Current follow-up question: What about tests?",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
        promoted_document_ids=[promoted_document_id],
    )

    result = await RetrievalAgent(cast("HybridRetrievalService", _FakeRetrievalService())).retrieve(state)

    assert result.sources[0].document_id == promoted_document_id


class _DraftRetrievalService:
    async def retrieve(
        self,
        *,
        query: str,
        user_id: uuid.UUID,
        limit: int,
        collection_id: uuid.UUID | None,
        tag_names: tuple[str, ...] | None = None,
        document_types: tuple[DocumentType, ...] | None = None,
        document_ids: tuple[uuid.UUID, ...] | None = None,
    ) -> list[QuerySourceDTO]:
        return [
            QuerySourceDTO(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_title="Python Generators",
                content="Python generators yield values lazily and are useful for memory-efficient iteration.",
                page_number=None,
                chunk_index=0,
                score=0.9,
            )
        ]


async def test_retrieval_agent_uses_explicit_relevance_query_for_drafts() -> None:
    state = ConseriumQueryState(
        query="Write a Markdown draft using only saved Conserium materials about Python generators.",
        retrieval_query="Python generators",
        relevance_query="Python generators",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
    )

    result = await RetrievalAgent(cast("HybridRetrievalService", _DraftRetrievalService())).retrieve(state)

    assert [source.document_title for source in result.sources] == ["Python Generators"]


async def test_retrieval_agent_keeps_ranked_context_when_explicit_relevance_filter_is_too_strict() -> None:
    state = ConseriumQueryState(
        query="Write a Markdown draft using only saved Conserium materials.",
        retrieval_query="Python generators",
        relevance_query="article outline",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
    )

    result = await RetrievalAgent(cast("HybridRetrievalService", _DraftRetrievalService())).retrieve(state)

    assert [source.document_title for source in result.sources] == ["Python Generators"]
    assert result.filtered_sources == []


async def test_retrieval_agent_filters_to_notes_when_query_requests_notes_only() -> None:
    service = _FakeRetrievalService()
    state = ConseriumQueryState(
        query="from my notes only give me a quote about sql",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
    )

    await RetrievalAgent(cast("HybridRetrievalService", service)).retrieve(state)

    assert service.received_document_types == (DocumentType.MARKDOWN,)
    assert service.received_query == "give me a quote about sql"


async def test_retrieval_agent_prefers_explicit_document_type_filter() -> None:
    service = _FakeRetrievalService()
    state = ConseriumQueryState(
        query="give me a quote about sql",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
        document_types=(DocumentType.MARKDOWN,),
    )

    await RetrievalAgent(cast("HybridRetrievalService", service)).retrieve(state)

    assert service.received_document_types == (DocumentType.MARKDOWN,)
    assert service.received_query == "give me a quote about sql"


class _NoiseRetrievalService:
    async def retrieve(
        self,
        *,
        query: str,
        user_id: uuid.UUID,
        limit: int,
        collection_id: uuid.UUID | None,
        tag_names: tuple[str, ...] | None = None,
        document_types: tuple[DocumentType, ...] | None = None,
        document_ids: tuple[uuid.UUID, ...] | None = None,
    ) -> list[QuerySourceDTO]:
        return [
            QuerySourceDTO(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_title="Architecture",
                content="Clean Architecture keeps dependencies inward across application layers.",
                page_number=None,
                chunk_index=0,
                score=0.9,
            ),
            QuerySourceDTO(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_title="Noise",
                content="Invoice payment bananas blue calendar placeholder unrelated synthetic noise.",
                page_number=None,
                chunk_index=1,
                score=0.8,
            ),
        ]


async def test_retrieval_agent_filters_unrelated_noise_sources() -> None:
    state = ConseriumQueryState(
        query="What is the Clean Architecture dependency rule?",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
    )

    result = await RetrievalAgent(cast("HybridRetrievalService", _NoiseRetrievalService())).retrieve(state)

    assert [source.document_title for source in result.sources] == ["Architecture"]
    assert [source.document_title for source in result.filtered_sources] == ["Noise"]


class _AuthNoiseRetrievalService:
    async def retrieve(
        self,
        *,
        query: str,
        user_id: uuid.UUID,
        limit: int,
        collection_id: uuid.UUID | None,
        tag_names: tuple[str, ...] | None = None,
        document_types: tuple[DocumentType, ...] | None = None,
        document_ids: tuple[uuid.UUID, ...] | None = None,
    ) -> list[QuerySourceDTO]:
        return [
            QuerySourceDTO(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_title="Live Eval - Refresh Token Revocation",
                content="Logout everywhere revokes refresh tokens by deleting Redis refresh keys for the user.",
                page_number=None,
                chunk_index=0,
                score=0.9,
            ),
            QuerySourceDTO(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_title="Live Eval Noise - Storage Archive",
                content="Columnar storage engine notes mention parquet lakehouse compression and archive partitions.",
                page_number=None,
                chunk_index=1,
                score=0.8,
            ),
        ]


async def test_retrieval_agent_returns_empty_sources_for_collection_scoped_noise() -> None:
    state = ConseriumQueryState(
        query="Which database storage engine is recommended in this Auth collection?",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        limit=5,
    )

    result = await RetrievalAgent(cast("HybridRetrievalService", _AuthNoiseRetrievalService())).retrieve(state)

    assert result.sources == []
    assert [source.document_title for source in result.filtered_sources] == [
        "Live Eval - Refresh Token Revocation",
        "Live Eval Noise - Storage Archive",
    ]


class _RecordingLLMService:
    def __init__(self) -> None:
        self.called = False
        self.received_query: str | None = None

    async def synthesize_answer(self, *, query: str, context: RefragContextPackage) -> str:
        self.called = True
        self.received_query = query
        return "LLM answer"


async def test_synthesis_agent_abstains_without_selected_context() -> None:
    llm_service = _RecordingLLMService()
    state = ConseriumQueryState(
        query="Which database storage engine is recommended in this Auth collection?",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
        refrag_context=RefragContextPackage(
            query="Which database storage engine is recommended in this Auth collection?",
            full_text_chunks=[],
            compressed_chunks=[],
            discarded_chunks=[],
            total_original_tokens=0,
            total_context_tokens=0,
            compression_strategy="test",
        ),
    )

    result = await SynthesisAgent(cast("ILLMService", llm_service)).synthesize(state)

    assert result.answer == ABSTENTION_ANSWER
    assert llm_service.called is False


async def test_synthesis_agent_applies_answer_language_preference() -> None:
    llm_service = _RecordingLLMService()
    state = ConseriumQueryState(
        query="Summarize the source",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
        answer_language="ukrainian",
        refrag_context=RefragContextPackage(
            query="Summarize the source",
            full_text_chunks=[
                RefragChunk(
                    chunk_id=uuid.uuid4(),
                    document_id=uuid.uuid4(),
                    document_title="Source",
                    original_text="Saved context",
                    context_text="Saved context",
                    representation=RefragRepresentation.FULL_TEXT,
                    page_number=None,
                    chunk_index=0,
                    score=0.8,
                    original_token_count=2,
                    context_token_count=2,
                ),
            ],
            compressed_chunks=[],
            discarded_chunks=[],
            total_original_tokens=2,
            total_context_tokens=2,
            compression_strategy="test",
        ),
    )

    await SynthesisAgent(cast("ILLMService", llm_service)).synthesize(state)

    assert llm_service.received_query == "Summarize the source\n\nAnswer language: Ukrainian."
