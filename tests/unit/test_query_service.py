import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.documents.repository import (
    ChunkSearchResult,
    DocumentActivityEventType,
    DocumentActivitySummary,
)
from src.documents.types import DocumentType
from src.kit.ai.embedding_provider import EmbeddingProvider
from src.kit.ai.llm_service import LLMService
from src.kit.cache.redis_conversation_store import RedisConversationStore
from src.kit.exceptions import QueryValidationException, ResourceNotFoundException
from src.models.chunk import ChunkModel
from src.query.agents.conversation_context_agent import ConversationContextAgent
from src.query.agents.graph_runner import QueryGraphRunner
from src.query.agents.refrag_context_agent import RefragContextAgent
from src.query.agents.retrieval_agent import RetrievalAgent
from src.query.agents.router_agent import RouterAgent
from src.query.agents.state import ConseriumQueryState
from src.query.agents.synthesis_agent import SynthesisAgent
from src.query.schemas import ConversationTurn, QueryInput, RefragContextPackage
from src.query.service import QueryExecutor
from src.query.services.query.conversation import QueryConversationService
from src.query.services.query.orchestration import QueryOrchestrationService
from src.query.services.query.persistence import QueryPersistenceService
from src.query.services.refrag.heuristic_context_builder import HeuristicRefragContextBuilder
from src.query.services.retrieval.hybrid_retrieval_service import HybridRetrievalService

if TYPE_CHECKING:
    from src.query.agents.eval_agent import EvalAgent
    from src.query.schemas import QueryEvaluationRecord


class _FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.embedded_texts: list[str] = []

    async def embed_text(self, text: str) -> list[float]:
        self.embedded_texts.append(text)
        return [0.1] * ChunkModel.EMBEDDING_DIMENSIONS

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.embedded_texts.extend(texts)
        return [[0.1] * ChunkModel.EMBEDDING_DIMENSIONS for _ in texts]


class _FakeChunkRepository:
    def __init__(self, chunks: list[ChunkModel]) -> None:
        self._chunks = chunks
        self.received_embedding: list[float] | None = None
        self.received_user_id: uuid.UUID | None = None
        self.received_document_ids: tuple[uuid.UUID, ...] | None = None

    async def hybrid_search(
        self,
        *,
        query: str,
        embedding: list[float],
        user_id: uuid.UUID,
        limit: int = 10,
        collection_id: uuid.UUID | None = None,
        tag_names: tuple[str, ...] | None = None,
        document_types: tuple[DocumentType, ...] | None = None,
        document_ids: tuple[uuid.UUID, ...] | None = None,
    ) -> list[ChunkSearchResult]:
        self.received_embedding = embedding
        self.received_user_id = user_id
        self.received_document_ids = document_ids
        return [
            ChunkSearchResult(chunk=chunk, document_title="Architecture Notes", score=0.5)
            for chunk in self._chunks[:limit]
        ]


class _FakeLLMService:
    def __init__(self) -> None:
        self.received_context: RefragContextPackage | None = None

    async def synthesize_answer(self, *, query: str, context: RefragContextPackage) -> str:
        self.received_context = context
        return "Synthesized answer [1]"


class _FakeRepositorySession:
    def __init__(self, chunk_repo: _FakeChunkRepository) -> None:
        self.chunk_repo = chunk_repo
        self.document_activity_repo = _FakeDocumentActivityRepository()
        self.chat_repo = _FakeChatRepository()
        self.collection_repo = _FakeCollectionRepository()
        self.search_query_repo = _FakeSearchQueryRepository()
        self.flush_count = 0

    async def __aenter__(self) -> "_FakeRepositorySession":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def flush(self) -> None:
        self.flush_count += 1

    async def rollback(self) -> None:
        return None


class _FakeDocumentActivityRepository:
    def __init__(self) -> None:
        self.events: list[tuple[uuid.UUID, uuid.UUID, DocumentActivityEventType]] = []

    async def record_event(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        event_type: DocumentActivityEventType,
    ) -> None:
        self.events.append((user_id, document_id, event_type))

    async def summarize_by_document_ids(
        self,
        *,
        user_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, DocumentActivitySummary]:
        return {}


class _FakeSearchQueryRepository:
    def __init__(self) -> None:
        self.records: list[object] = []

    async def record_query(self, record: object) -> None:
        self.records.append(record)

    async def list_recent_by_document(self, *, user_id: uuid.UUID, document_id: uuid.UUID, limit: int) -> list[object]:
        return []

    async def list_recent_by_collection(self, *, user_id: uuid.UUID, collection_id: uuid.UUID, limit: int) -> list[object]:
        return []


class _FakeChatRepository:
    def __init__(self) -> None:
        self.session: object | None = None
        self.created_sessions: list[tuple[uuid.UUID, uuid.UUID | None, str]] = []
        self.persisted_turns: list[ConversationTurn] = []
        self.messages: list[tuple[str, str]] = []
        self.get_recent_turns_count = 0

    async def get_session(self, *, user_id: uuid.UUID, chat_id: uuid.UUID) -> object | None:
        return self.session

    async def create_session(self, *, user_id: uuid.UUID, title: str, chat_id: uuid.UUID | None = None) -> object:
        self.created_sessions.append((user_id, chat_id, title))
        self.session = object()
        return self.session

    async def get_recent_turns(self, *, user_id: uuid.UUID, chat_id: uuid.UUID, limit: int) -> list[ConversationTurn]:
        self.get_recent_turns_count += 1
        return self.persisted_turns

    async def append_message(
        self,
        *,
        chat_id: uuid.UUID,
        role: str,
        content: str,
        sources: object | None = None,
        refrag_context: object | None = None,
        eval_scores: object | None = None,
        trace_id: str | None = None,
    ) -> object:
        self.messages.append((role, content))
        return object()


class _FailingChatRepository(_FakeChatRepository):
    async def append_message(
        self,
        *,
        chat_id: uuid.UUID,
        role: str,
        content: str,
        sources: object | None = None,
        refrag_context: object | None = None,
        eval_scores: object | None = None,
        trace_id: str | None = None,
    ) -> object:
        raise RuntimeError("chat write failed")


class _FakeCollection:
    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id


class _FakeCollectionRepository:
    def __init__(self) -> None:
        self.collection: _FakeCollection | None = None

    async def get_by_id(self, collection_id: uuid.UUID) -> _FakeCollection | None:
        return self.collection


class _FakeConversationStore:
    def __init__(self) -> None:
        self.recent_turns: list[ConversationTurn] = []
        self.requested_conversation_id: uuid.UUID | None = None
        self.appended_conversation_id: uuid.UUID | None = None
        self.appended_turn: ConversationTurn | None = None

    async def get_recent_turns(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        limit: int,
    ) -> list[ConversationTurn]:
        self.requested_conversation_id = conversation_id
        return self.recent_turns

    async def append_turn(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        turn: ConversationTurn,
        ttl_seconds: int,
    ) -> None:
        self.appended_conversation_id = conversation_id
        self.appended_turn = turn


class _FakeEvalAgent:
    async def evaluate(self, state: object) -> object:
        return state


def _as_embedding_provider(provider: _FakeEmbeddingProvider) -> EmbeddingProvider:
    return cast("EmbeddingProvider", provider)


def _as_llm_service(service: _FakeLLMService) -> LLMService:
    return cast("LLMService", service)


def _as_refrag_builder(builder: HeuristicRefragContextBuilder) -> HeuristicRefragContextBuilder:
    return cast("HeuristicRefragContextBuilder", builder)


def _query_orchestration(
    repository_session: _FakeRepositorySession,
    conversation_store: _FakeConversationStore,
) -> QueryOrchestrationService:
    return QueryOrchestrationService(
        QueryConversationService(
            _as_conversation_store(conversation_store),
            repository_session,  # type: ignore[arg-type]
            repository_session.chat_repo,  # type: ignore[arg-type]
            repository_session.collection_repo,  # type: ignore[arg-type]
        ),
        QueryPersistenceService(
            repository_session,  # type: ignore[arg-type]
            repository_session.chat_repo,  # type: ignore[arg-type]
            repository_session.document_activity_repo,  # type: ignore[arg-type]
            repository_session.search_query_repo,  # type: ignore[arg-type]
        ),
    )


def _as_conversation_store(store: _FakeConversationStore) -> RedisConversationStore:
    return cast("RedisConversationStore", store)


def _make_graph_runner(
    chunk_repo: _FakeChunkRepository,
    embedding_provider: _FakeEmbeddingProvider,
    refrag_builder: HeuristicRefragContextBuilder,
    llm_service: _FakeLLMService,
) -> QueryGraphRunner:
    retrieval_service = HybridRetrievalService(
        chunk_repo,  # type: ignore[arg-type]
        _as_embedding_provider(embedding_provider),
    )
    return QueryGraphRunner(
        ConversationContextAgent(),
        RouterAgent(),
        RetrievalAgent(retrieval_service),
        RefragContextAgent(_as_refrag_builder(refrag_builder)),
        SynthesisAgent(_as_llm_service(llm_service)),
        cast("EvalAgent", _FakeEvalAgent()),
    )


async def test_query_service_embeds_query_and_returns_sources() -> None:
    user_id = uuid.uuid4()
    chunk = ChunkModel.create(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="Clean Architecture keeps dependencies inward.",
        embedding=[0.2] * ChunkModel.EMBEDDING_DIMENSIONS,
        chunk_index=0,
        page_number=3,
    )
    chunk_repo = _FakeChunkRepository([chunk])
    embedding_provider = _FakeEmbeddingProvider()
    llm_service = _FakeLLMService()
    graph_runner = _make_graph_runner(chunk_repo, embedding_provider, HeuristicRefragContextBuilder(), llm_service)
    conversation_store = _FakeConversationStore()
    repository_session = _FakeRepositorySession(chunk_repo)
    conversation_id = uuid.uuid4()
    handler = QueryExecutor(graph_runner, _query_orchestration(repository_session, conversation_store))

    result = await handler(
        QueryInput(user_id=user_id, conversation_id=conversation_id, query="  Clean Architecture  ", limit=5)
    )

    assert embedding_provider.embedded_texts == ["Clean Architecture"]
    assert chunk_repo.received_user_id == user_id
    assert result.conversation_id == conversation_id
    assert result.query == "Clean Architecture"
    assert result.sources[0].chunk_id == chunk.id
    assert result.sources[0].document_title == "Architecture Notes"
    assert result.sources[0].page_number == 3
    assert result.answer == "Synthesized answer [1]"
    assert llm_service.received_context is not None
    assert llm_service.received_context.full_text_chunks[0].chunk_id == chunk.id
    assert result.refrag_context.full_text_chunks[0].chunk_id == chunk.id
    assert conversation_store.requested_conversation_id == conversation_id
    assert conversation_store.appended_conversation_id == conversation_id
    assert conversation_store.appended_turn is not None
    assert conversation_store.appended_turn.answer == "Synthesized answer [1]"
    assert len(repository_session.search_query_repo.records) == 1


async def test_query_service_scopes_retrieval_to_document_id() -> None:
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    chunk = ChunkModel.create(
        id=uuid.uuid4(),
        document_id=document_id,
        content="Scoped document content explains vector search.",
        embedding=[0.2] * ChunkModel.EMBEDDING_DIMENSIONS,
        chunk_index=0,
    )
    chunk_repo = _FakeChunkRepository([chunk])
    graph_runner = _make_graph_runner(
        chunk_repo,
        _FakeEmbeddingProvider(),
        HeuristicRefragContextBuilder(),
        _FakeLLMService(),
    )
    repository_session = _FakeRepositorySession(chunk_repo)
    handler = QueryExecutor(graph_runner, _query_orchestration(repository_session, _FakeConversationStore()))

    await handler(QueryInput(user_id=user_id, query="Explain this", document_ids=(document_id,), limit=5))

    record = cast("QueryEvaluationRecord", repository_session.search_query_repo.records[0])
    assert chunk_repo.received_document_ids == (document_id,)
    assert record.document_ids == (document_id,)


async def test_query_service_rejects_blank_query() -> None:
    graph_runner = _make_graph_runner(
        _FakeChunkRepository([]),
        _FakeEmbeddingProvider(),
        HeuristicRefragContextBuilder(),
        _FakeLLMService(),
    )
    handler = QueryExecutor(
        graph_runner,
        _query_orchestration(_FakeRepositorySession(_FakeChunkRepository([])), _FakeConversationStore()),
    )

    with pytest.raises(QueryValidationException, match="query cannot be empty"):
        await handler(QueryInput(user_id=uuid.uuid4(), query="  "))


async def test_query_interaction_persistence_uses_single_flush() -> None:
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    repository_session = _FakeRepositorySession(_FakeChunkRepository([]))
    service = _query_orchestration(repository_session, _FakeConversationStore())
    state = ConseriumQueryState(query="hello", user_id=user_id, conversation_id=conversation_id, limit=5, answer="answer")

    await service.record_interaction(
        QueryInput(user_id=user_id, query="hello", limit=5),
        query="hello",
        state=state,
        latency_ms=10,
        refrag_context={},
        conversation_id=conversation_id,
    )

    assert len(repository_session.search_query_repo.records) == 1
    assert repository_session.chat_repo.messages == [("user", "hello"), ("assistant", "answer")]
    assert repository_session.flush_count == 1


async def test_query_interaction_does_not_flush_partial_state_when_chat_write_fails() -> None:
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    repository_session = _FakeRepositorySession(_FakeChunkRepository([]))
    repository_session.chat_repo = _FailingChatRepository()
    service = _query_orchestration(repository_session, _FakeConversationStore())
    state = ConseriumQueryState(query="hello", user_id=user_id, conversation_id=conversation_id, limit=5, answer="answer")

    with pytest.raises(RuntimeError, match="chat write failed"):
        await service.record_interaction(
            QueryInput(user_id=user_id, query="hello", limit=5),
            query="hello",
            state=state,
            latency_ms=10,
            refrag_context={},
            conversation_id=conversation_id,
        )

    assert repository_session.flush_count == 0


async def test_query_orchestration_creates_chat_session_if_missing() -> None:
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    repository_session = _FakeRepositorySession(_FakeChunkRepository([]))
    service = _query_orchestration(repository_session, _FakeConversationStore())

    await service.prepare_context(
        QueryInput(user_id=user_id, query="Explain Clean Architecture", limit=5),
        query="Explain Clean Architecture",
        conversation_id=conversation_id,
    )

    assert repository_session.chat_repo.created_sessions == [(user_id, conversation_id, "Explain Clean Architecture")]


async def test_query_orchestration_does_not_recreate_existing_chat_session() -> None:
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    repository_session = _FakeRepositorySession(_FakeChunkRepository([]))
    repository_session.chat_repo.session = object()
    service = _query_orchestration(repository_session, _FakeConversationStore())

    await service.prepare_context(
        QueryInput(user_id=user_id, query="Explain Clean Architecture", limit=5),
        query="Explain Clean Architecture",
        conversation_id=conversation_id,
    )

    assert repository_session.chat_repo.created_sessions == []


async def test_query_orchestration_loads_redis_turns_before_persisted_turns() -> None:
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    redis_turn = ConversationTurn(query="redis", answer="turn", sources=[], created_at=datetime.now(UTC))
    persisted_turn = ConversationTurn(query="db", answer="turn", sources=[], created_at=datetime.now(UTC))
    repository_session = _FakeRepositorySession(_FakeChunkRepository([]))
    repository_session.chat_repo.persisted_turns = [persisted_turn]
    conversation_store = _FakeConversationStore()
    conversation_store.recent_turns = [redis_turn]
    service = _query_orchestration(repository_session, conversation_store)

    turns = await service.prepare_context(
        QueryInput(user_id=user_id, query="Explain Clean Architecture", limit=5),
        query="Explain Clean Architecture",
        conversation_id=conversation_id,
    )

    assert turns == [redis_turn]
    assert repository_session.chat_repo.get_recent_turns_count == 0


async def test_query_orchestration_falls_back_to_persisted_turns() -> None:
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    persisted_turn = ConversationTurn(query="db", answer="turn", sources=[], created_at=datetime.now(UTC))
    repository_session = _FakeRepositorySession(_FakeChunkRepository([]))
    repository_session.chat_repo.persisted_turns = [persisted_turn]
    service = _query_orchestration(repository_session, _FakeConversationStore())

    turns = await service.prepare_context(
        QueryInput(user_id=user_id, query="Explain Clean Architecture", limit=5),
        query="Explain Clean Architecture",
        conversation_id=conversation_id,
    )

    assert turns == [persisted_turn]
    assert repository_session.chat_repo.get_recent_turns_count == 1


async def test_query_orchestration_collection_ownership_failure_stops_before_session_creation() -> None:
    user_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    repository_session = _FakeRepositorySession(_FakeChunkRepository([]))
    repository_session.collection_repo.collection = _FakeCollection(user_id=uuid.uuid4())
    service = _query_orchestration(repository_session, _FakeConversationStore())

    with pytest.raises(ResourceNotFoundException, match="collection not found"):
        await service.prepare_context(
            QueryInput(user_id=user_id, query="Explain Clean Architecture", collection_id=collection_id, limit=5),
            query="Explain Clean Architecture",
            conversation_id=uuid.uuid4(),
        )

    assert repository_session.chat_repo.created_sessions == []
