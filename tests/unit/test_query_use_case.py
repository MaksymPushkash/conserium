import uuid
from typing import cast

import pytest

from src.application.agents.query.conversation_context_agent import ConversationContextAgent
from src.application.agents.query.graph_runner import QueryGraphRunner
from src.application.agents.query.refrag_context_agent import RefragContextAgent
from src.application.agents.query.retrieval_agent import RetrievalAgent
from src.application.agents.query.router_agent import RouterAgent
from src.application.agents.query.synthesis_agent import SynthesisAgent
from src.application.dtos.conversation_dtos import ConversationTurnDTO
from src.application.dtos.query_dtos import QueryDTO
from src.application.dtos.refrag_dtos import RefragContextPackage
from src.application.ports.ai.embedding_provider import IEmbeddingProvider
from src.application.ports.ai.llm_service import ILLMService
from src.application.ports.conversations.conversation_store import IConversationStore
from src.application.ports.persistence.chunk_repository import ChunkSearchResult
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.ports.refrag.refrag_context_builder import IRefragContextBuilder
from src.application.services.refrag.heuristic_context_builder import HeuristicRefragContextBuilder
from src.application.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from src.application.use_cases.query.query_use_case import QueryUseCase
from src.domain.entities.chunk_entity import ChunkEntity


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

    async def hybrid_search(
        self,
        *,
        query: str,
        embedding: list[float],
        user_id: uuid.UUID,
        limit: int = 10,
        collection_id: uuid.UUID | None = None,
    ) -> list[ChunkSearchResult]:
        self.received_embedding = embedding
        self.received_user_id = user_id
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

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _FakeConversationStore:
    def __init__(self) -> None:
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
        return []

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
    conversation_id = uuid.uuid4()
    use_case = QueryUseCase(graph_runner, _as_conversation_store(conversation_store))

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


async def test_query_use_case_rejects_blank_query() -> None:
    graph_runner = _make_graph_runner(
        _FakeChunkRepository([]),
        _FakeEmbeddingProvider(),
        HeuristicRefragContextBuilder(),
        _FakeLLMService(),
    )
    use_case = QueryUseCase(graph_runner, _as_conversation_store(_FakeConversationStore()))

    with pytest.raises(ValueError, match="query cannot be empty"):
        await use_case(QueryDTO(user_id=uuid.uuid4(), query="  "))
