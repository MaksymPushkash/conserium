import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from src.application.agents.query.conversation_context_agent import ConversationContextAgent
from src.application.agents.query.retrieval_agent import RetrievalAgent
from src.application.agents.query.router_agent import RouterAgent
from src.application.agents.query.state import CortexQueryState, QueryType
from src.application.dtos.conversation_dtos import ConversationSourceDTO, ConversationTurnDTO
from src.application.dtos.query_dtos import QuerySourceDTO
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.services.retrieval.hybrid_retrieval_service import HybridRetrievalService


def test_router_agent_marks_summary_queries() -> None:
    state = CortexQueryState(
        query="Summarize my notes about startup development",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
    )

    routed_state = RouterAgent().route(state)

    assert routed_state.query_type == QueryType.SUMMARY


def test_router_agent_defaults_to_search() -> None:
    state = CortexQueryState(
        query="What did I read about Clean Architecture?",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
    )

    routed_state = RouterAgent().route(state)

    assert routed_state.query_type == QueryType.SEARCH


def test_conversation_context_agent_rewrites_follow_up_query_and_promotes_sources() -> None:
    document_id = uuid.uuid4()
    state = CortexQueryState(
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
    state = CortexQueryState(
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


def test_conversation_context_agent_does_not_rewrite_short_standalone_query() -> None:
    previous_document_id = uuid.uuid4()
    state = CortexQueryState(
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
    state = CortexQueryState(
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

    async def retrieve(
        self,
        *,
        query: str,
        user_id: uuid.UUID,
        limit: int,
        collection_id: uuid.UUID | None,
        tag_names: tuple[str, ...] | None = None,
        document_types: tuple[DocumentType, ...] | None = None,
    ) -> list[QuerySourceDTO]:
        self.received_query = query
        self.received_tag_names = tag_names
        self.received_document_types = document_types
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
    state = CortexQueryState(
        query="What about tests?",
        retrieval_query="Current follow-up question: What about tests?",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
        promoted_document_ids=[promoted_document_id],
    )

    result = await RetrievalAgent(cast("HybridRetrievalService", _FakeRetrievalService())).retrieve(state)

    assert result.sources[0].document_id == promoted_document_id


async def test_retrieval_agent_filters_to_notes_when_query_requests_notes_only() -> None:
    service = _FakeRetrievalService()
    state = CortexQueryState(
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
    state = CortexQueryState(
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
    state = CortexQueryState(
        query="What is the Clean Architecture dependency rule?",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
    )

    result = await RetrievalAgent(cast("HybridRetrievalService", _NoiseRetrievalService())).retrieve(state)

    assert [source.document_title for source in result.sources] == ["Architecture"]
    assert [source.document_title for source in result.filtered_sources] == ["Noise"]
