import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.application.agents.query.conversation_context_agent import ConversationContextAgent
from src.application.agents.query.graph_runner import QueryGraphRunner
from src.application.agents.query.refrag_context_agent import RefragContextAgent
from src.application.agents.query.retrieval_agent import RetrievalAgent
from src.application.agents.query.router_agent import RouterAgent
from src.application.agents.query.state import ConseriumQueryState
from src.application.agents.query.synthesis_agent import SynthesisAgent
from src.application.dtos.conversation_dtos import ConversationTurnDTO
from src.application.dtos.query_dtos import QueryDTO
from src.application.dtos.refrag_dtos import RefragContextPackage
from src.application.ports.ai.embedding_provider import IEmbeddingProvider
from src.application.ports.ai.llm_service import ILLMService
from src.application.ports.conversations.conversation_store import IConversationStore
from src.application.ports.persistence.chunk_repository import ChunkSearchResult
from src.application.ports.persistence.document_activity_repository import (
    DocumentActivityEventType,
    DocumentActivitySummary,
)
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.ports.refrag.refrag_context_builder import IRefragContextBuilder
from src.application.services.query_orchestration import QueryOrchestrationService
from src.application.services.refrag.heuristic_context_builder import HeuristicRefragContextBuilder
from src.application.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from src.application.use_cases.query.query_use_case import QueryUseCase
from src.domain.entities.chunk_entity import ChunkEntity
from src.domain.exceptions import QueryValidationException, ResourceNotFoundException
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.agents.query.eval_agent import EvalAgent
    from src.application.dtos.evaluation_dtos import QueryEvaluationRecordDTO


class _FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.embedded_texts: list[str] = []

    async def embed_text(self, text: str) -> list[float]:
        self.embedded_texts.append(text)
        return [0.1] * ChunkEntity.EMBEDDING_DIMENSIONS

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.embedded_texts.extend(texts)
        return [[0.1] * ChunkEntity.EMBEDDING_DIMENSIONS for _ in texts]


class _FakeChunkRepository:
    def __init__(self, chunks: list[ChunkEntity]) -> None:
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


class _FakeUnitOfWork:
    def __init__(self, chunk_repo: _FakeChunkRepository) -> None:
        self.chunk_repo = chunk_repo
        self.document_activity_repo = _FakeDocumentActivityRepository()
        self.chat_repo = _FakeChatRepository()
        self.collection_repo = _FakeCollectionRepository()
        self.search_query_repo = _FakeSearchQueryRepository()
        self.commit_count = 0

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def commit(self) -> None:
        self.commit_count += 1

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
        self.persisted_turns: list[ConversationTurnDTO] = []
        self.messages: list[tuple[str, str]] = []
        self.get_recent_turns_count = 0

    async def get_session(self, *, user_id: uuid.UUID, chat_id: uuid.UUID) -> object | None:
        return self.session

    async def create_session(self, *, user_id: uuid.UUID, title: str, chat_id: uuid.UUID | None = None) -> object:
        self.created_sessions.append((user_id, chat_id, title))
        self.session = object()
        return self.session

    async def get_recent_turns(self, *, user_id: uuid.UUID, chat_id: uuid.UUID, limit: int) -> list[ConversationTurnDTO]:
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
        self.recent_turns: list[ConversationTurnDTO] = []
        self.requested_conversation_id: uuid.UUID | None = None
        self.appended_conversation_id: uuid.UUID | None = None
        self.appended_turn: ConversationTurnDTO | None = None

    async def get_recent_turns(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        limit: int,
    ) -> list[ConversationTurnDTO]:
        self.requested_conversation_id = conversation_id
        return self.recent_turns

    async def append_turn(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        turn: ConversationTurnDTO,
        ttl_seconds: int,
    ) -> None:
        self.appended_conversation_id = conversation_id
        self.appended_turn = turn


class _FakeEvalAgent:
    async def evaluate(self, state: object) -> object:
        return state


def _as_embedding_provider(provider: _FakeEmbeddingProvider) -> IEmbeddingProvider:
    return cast("IEmbeddingProvider", provider)


def _as_llm_service(service: _FakeLLMService) -> ILLMService:
    return cast("ILLMService", service)


def _as_refrag_builder(builder: HeuristicRefragContextBuilder) -> IRefragContextBuilder:
    return cast("IRefragContextBuilder", builder)


def _as_uow(uow: _FakeUnitOfWork) -> IUnitOfWork:
    return cast("IUnitOfWork", uow)


def _as_conversation_store(store: _FakeConversationStore) -> IConversationStore:
    return cast("IConversationStore", store)


def _make_graph_runner(
    chunk_repo: _FakeChunkRepository,
    embedding_provider: _FakeEmbeddingProvider,
    refrag_builder: HeuristicRefragContextBuilder,
    llm_service: _FakeLLMService,
) -> QueryGraphRunner:
    retrieval_service = HybridRetrievalService(
        _as_uow(_FakeUnitOfWork(chunk_repo)),
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


async def test_query_use_case_embeds_query_and_returns_sources() -> None:
    user_id = uuid.uuid4()
    chunk = ChunkEntity.create(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="Clean Architecture keeps dependencies inward.",
        embedding=[0.2] * ChunkEntity.EMBEDDING_DIMENSIONS,
        chunk_index=0,
        page_number=3,
    )
    chunk_repo = _FakeChunkRepository([chunk])
    embedding_provider = _FakeEmbeddingProvider()
    llm_service = _FakeLLMService()
    graph_runner = _make_graph_runner(chunk_repo, embedding_provider, HeuristicRefragContextBuilder(), llm_service)
    conversation_store = _FakeConversationStore()
    uow = _FakeUnitOfWork(chunk_repo)
    conversation_id = uuid.uuid4()
    use_case = QueryUseCase(graph_runner, _as_conversation_store(conversation_store), _as_uow(uow))

    result = await use_case(
        QueryDTO(user_id=user_id, conversation_id=conversation_id, query="  Clean Architecture  ", limit=5)
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
    assert len(uow.search_query_repo.records) == 1


async def test_query_use_case_scopes_retrieval_to_document_id() -> None:
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    chunk = ChunkEntity.create(
        id=uuid.uuid4(),
        document_id=document_id,
        content="Scoped document content explains vector search.",
        embedding=[0.2] * ChunkEntity.EMBEDDING_DIMENSIONS,
        chunk_index=0,
    )
    chunk_repo = _FakeChunkRepository([chunk])
    graph_runner = _make_graph_runner(
        chunk_repo,
        _FakeEmbeddingProvider(),
        HeuristicRefragContextBuilder(),
        _FakeLLMService(),
    )
    uow = _FakeUnitOfWork(chunk_repo)
    use_case = QueryUseCase(graph_runner, _as_conversation_store(_FakeConversationStore()), _as_uow(uow))

    await use_case(QueryDTO(user_id=user_id, query="Explain this", document_ids=(document_id,), limit=5))

    record = cast("QueryEvaluationRecordDTO", uow.search_query_repo.records[0])
    assert chunk_repo.received_document_ids == (document_id,)
    assert record.document_ids == (document_id,)


async def test_query_use_case_rejects_blank_query() -> None:
    graph_runner = _make_graph_runner(
        _FakeChunkRepository([]),
        _FakeEmbeddingProvider(),
        HeuristicRefragContextBuilder(),
        _FakeLLMService(),
    )
    use_case = QueryUseCase(
        graph_runner,
        _as_conversation_store(_FakeConversationStore()),
        _as_uow(_FakeUnitOfWork(_FakeChunkRepository([]))),
    )

    with pytest.raises(QueryValidationException, match="query cannot be empty"):
        await use_case(QueryDTO(user_id=uuid.uuid4(), query="  "))


async def test_query_interaction_persistence_uses_single_commit() -> None:
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    uow = _FakeUnitOfWork(_FakeChunkRepository([]))
    service = QueryOrchestrationService(_as_conversation_store(_FakeConversationStore()), _as_uow(uow))
    state = ConseriumQueryState(query="hello", user_id=user_id, conversation_id=conversation_id, limit=5, answer="answer")

    await service.record_interaction(
        QueryDTO(user_id=user_id, query="hello", limit=5),
        query="hello",
        state=state,
        latency_ms=10,
        refrag_context={},
        conversation_id=conversation_id,
    )

    assert len(uow.search_query_repo.records) == 1
    assert uow.chat_repo.messages == [("user", "hello"), ("assistant", "answer")]
    assert uow.commit_count == 1


async def test_query_interaction_does_not_commit_partial_state_when_chat_write_fails() -> None:
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    uow = _FakeUnitOfWork(_FakeChunkRepository([]))
    uow.chat_repo = _FailingChatRepository()
    service = QueryOrchestrationService(_as_conversation_store(_FakeConversationStore()), _as_uow(uow))
    state = ConseriumQueryState(query="hello", user_id=user_id, conversation_id=conversation_id, limit=5, answer="answer")

    with pytest.raises(RuntimeError, match="chat write failed"):
        await service.record_interaction(
            QueryDTO(user_id=user_id, query="hello", limit=5),
            query="hello",
            state=state,
            latency_ms=10,
            refrag_context={},
            conversation_id=conversation_id,
        )

    assert uow.commit_count == 0


async def test_query_orchestration_creates_chat_session_if_missing() -> None:
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    uow = _FakeUnitOfWork(_FakeChunkRepository([]))
    service = QueryOrchestrationService(_as_conversation_store(_FakeConversationStore()), _as_uow(uow))

    await service.prepare_context(
        QueryDTO(user_id=user_id, query="Explain Clean Architecture", limit=5),
        query="Explain Clean Architecture",
        conversation_id=conversation_id,
    )

    assert uow.chat_repo.created_sessions == [(user_id, conversation_id, "Explain Clean Architecture")]


async def test_query_orchestration_does_not_recreate_existing_chat_session() -> None:
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    uow = _FakeUnitOfWork(_FakeChunkRepository([]))
    uow.chat_repo.session = object()
    service = QueryOrchestrationService(_as_conversation_store(_FakeConversationStore()), _as_uow(uow))

    await service.prepare_context(
        QueryDTO(user_id=user_id, query="Explain Clean Architecture", limit=5),
        query="Explain Clean Architecture",
        conversation_id=conversation_id,
    )

    assert uow.chat_repo.created_sessions == []


async def test_query_orchestration_loads_redis_turns_before_persisted_turns() -> None:
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    redis_turn = ConversationTurnDTO(query="redis", answer="turn", sources=[], created_at=datetime.now(UTC))
    persisted_turn = ConversationTurnDTO(query="db", answer="turn", sources=[], created_at=datetime.now(UTC))
    uow = _FakeUnitOfWork(_FakeChunkRepository([]))
    uow.chat_repo.persisted_turns = [persisted_turn]
    conversation_store = _FakeConversationStore()
    conversation_store.recent_turns = [redis_turn]
    service = QueryOrchestrationService(_as_conversation_store(conversation_store), _as_uow(uow))

    turns = await service.prepare_context(
        QueryDTO(user_id=user_id, query="Explain Clean Architecture", limit=5),
        query="Explain Clean Architecture",
        conversation_id=conversation_id,
    )

    assert turns == [redis_turn]
    assert uow.chat_repo.get_recent_turns_count == 0


async def test_query_orchestration_falls_back_to_persisted_turns() -> None:
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    persisted_turn = ConversationTurnDTO(query="db", answer="turn", sources=[], created_at=datetime.now(UTC))
    uow = _FakeUnitOfWork(_FakeChunkRepository([]))
    uow.chat_repo.persisted_turns = [persisted_turn]
    service = QueryOrchestrationService(_as_conversation_store(_FakeConversationStore()), _as_uow(uow))

    turns = await service.prepare_context(
        QueryDTO(user_id=user_id, query="Explain Clean Architecture", limit=5),
        query="Explain Clean Architecture",
        conversation_id=conversation_id,
    )

    assert turns == [persisted_turn]
    assert uow.chat_repo.get_recent_turns_count == 1


async def test_query_orchestration_collection_ownership_failure_stops_before_session_creation() -> None:
    user_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    uow = _FakeUnitOfWork(_FakeChunkRepository([]))
    uow.collection_repo.collection = _FakeCollection(user_id=uuid.uuid4())
    service = QueryOrchestrationService(_as_conversation_store(_FakeConversationStore()), _as_uow(uow))

    with pytest.raises(ResourceNotFoundException, match="collection not found"):
        await service.prepare_context(
            QueryDTO(user_id=user_id, query="Explain Clean Architecture", collection_id=collection_id, limit=5),
            query="Explain Clean Architecture",
            conversation_id=uuid.uuid4(),
        )

    assert uow.chat_repo.created_sessions == []
