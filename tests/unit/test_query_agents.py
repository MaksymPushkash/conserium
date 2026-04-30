import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from src.application.agents.query.conversation_context_agent import ConversationContextAgent
from src.application.agents.query.retrieval_agent import RetrievalAgent
from src.application.agents.query.router_agent import RouterAgent
from src.application.agents.query.state import CortexQueryState, QueryType
from src.application.dtos.conversation_dtos import ConversationSourceDTO, ConversationTurnDTO
from src.application.dtos.query_dtos import QuerySourceDTO

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
    state = CortexQueryState(
        query="PostgreSQL indexes",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
        conversation_turns=[
            ConversationTurnDTO(
                query="What did I read about Clean Architecture?",
                answer="You read that dependencies should point inward.",
                sources=[],
                created_at=datetime.now(UTC),
            )
        ],
    )

    result = ConversationContextAgent().apply(state)

    assert result.retrieval_query == "PostgreSQL indexes"


class _FakeRetrievalService:
    async def retrieve(
        self,
        *,
        query: str,
        user_id: uuid.UUID,
        limit: int,
        collection_id: uuid.UUID | None,
    ) -> list[QuerySourceDTO]:
        promoted_document_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        other_document_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
        return [
            QuerySourceDTO(
                chunk_id=uuid.uuid4(),
                document_id=other_document_id,
                document_title="Other",
                content="Other content",
                page_number=None,
                chunk_index=0,
                score=0.9,
            ),
            QuerySourceDTO(
                chunk_id=uuid.uuid4(),
                document_id=promoted_document_id,
                document_title="Previous Source",
                content="Previous source content",
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
