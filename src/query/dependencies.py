from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.chats.repository import ChatRepository
from src.collections.repository import CollectionRepository
from src.documents.activity_repository import DocumentActivityRepository
from src.documents.chunk_repository import ChunkRepository
from src.kit.ai.embedding_provider import EmbeddingProvider
from src.kit.ai.llm_service import LLMService, StreamingLLMService
from src.kit.ai.providers.cached_embedding_provider import CachedEmbeddingProvider
from src.kit.ai.providers.openai_embedding_provider import OpenAIEmbeddingProvider
from src.kit.ai.providers.openai_llm_service import OpenAILLMService
from src.kit.cache.redis import get_redis
from src.kit.cache.redis_cache import RedisCache
from src.kit.cache.redis_conversation_store import RedisConversationStore
from src.observability.langfuse_tracer import LangfuseQueryTracer
from src.postgres import get_db_session
from src.query.agents.conversation_context_agent import ConversationContextAgent
from src.query.agents.eval_agent import EvalAgent
from src.query.agents.graph_runner import QueryGraphRunner
from src.query.agents.refrag_context_agent import RefragContextAgent
from src.query.agents.retrieval_agent import RetrievalAgent
from src.query.agents.router_agent import RouterAgent
from src.query.agents.streaming_graph_runner import StreamingQueryGraphRunner
from src.query.agents.streaming_synthesis_agent import StreamingSynthesisAgent
from src.query.agents.synthesis_agent import SynthesisAgent
from src.query.repository import SearchQueryRepository
from src.query.service import QueryExecutor, StreamQueryExecutor
from src.query.services.evaluation.heuristic_ragas_scorer import HeuristicRagasScorer
from src.query.services.evaluation.ragas_eval_scorer import RagasEvalScorer
from src.query.services.evaluation.scorer import EvalScorer
from src.query.services.query.conversation import QueryConversationService
from src.query.services.query.orchestration import QueryOrchestrationService
from src.query.services.query.persistence import QueryPersistenceService
from src.query.services.refrag.heuristic_context_builder import HeuristicRefragContextBuilder
from src.query.services.retrieval.cross_encoder_reranker import CrossEncoderReranker
from src.query.services.retrieval.embedding_reranker import EmbeddingReranker
from src.query.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from src.query.services.retrieval.reranker import Reranker
from src.settings import settings


def get_cache(redis: Redis = Depends(get_redis)) -> RedisCache:
    return RedisCache(redis)


def get_conversation_store(cache: RedisCache = Depends(get_cache)) -> RedisConversationStore:
    return RedisConversationStore(cache)


def get_query_orchestration(
    session: AsyncSession = Depends(get_db_session),
    conversation_store: RedisConversationStore = Depends(get_conversation_store),
) -> QueryOrchestrationService:
    chat_repo = ChatRepository.from_session(session)
    return QueryOrchestrationService(
        QueryConversationService(
            conversation_store,
            session,
            chat_repo,
            CollectionRepository.from_session(session),
        ),
        QueryPersistenceService(
            session,
            chat_repo,
            DocumentActivityRepository.from_session(session),
            SearchQueryRepository.from_session(session),
        ),
    )


def get_embedding_provider(cache: RedisCache = Depends(get_cache)) -> EmbeddingProvider:
    return CachedEmbeddingProvider(OpenAIEmbeddingProvider(), cache)


def get_llm_service() -> LLMService:
    return OpenAILLMService()


def get_streaming_llm_service() -> StreamingLLMService:
    return OpenAILLMService()


def get_refrag_context_builder() -> HeuristicRefragContextBuilder:
    return HeuristicRefragContextBuilder()


def get_reranker(embedding_provider: EmbeddingProvider = Depends(get_embedding_provider)) -> Reranker:
    fallback = EmbeddingReranker(embedding_provider)
    if settings.RERANKER_BACKEND.lower() in {"cross_encoder", "cross-encoder"}:
        return CrossEncoderReranker(fallback=fallback)
    return fallback


def get_eval_scorer() -> EvalScorer:
    fallback = HeuristicRagasScorer()
    if settings.EVAL_SCORER.lower() == "ragas":
        return RagasEvalScorer(fallback=fallback)
    return fallback


def get_query_tracer() -> LangfuseQueryTracer:
    return LangfuseQueryTracer()


def get_query_graph_runner(
    session: AsyncSession = Depends(get_db_session),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    refrag_context_builder: HeuristicRefragContextBuilder = Depends(get_refrag_context_builder),
    llm_service: LLMService = Depends(get_llm_service),
    reranker: Reranker = Depends(get_reranker),
    eval_scorer: EvalScorer = Depends(get_eval_scorer),
    query_tracer: LangfuseQueryTracer = Depends(get_query_tracer),
) -> QueryGraphRunner:
    retrieval_service = HybridRetrievalService(ChunkRepository.from_session(session), embedding_provider)
    return QueryGraphRunner(
        ConversationContextAgent(),
        RouterAgent(),
        RetrievalAgent(retrieval_service, reranker),
        RefragContextAgent(refrag_context_builder),
        SynthesisAgent(llm_service),
        EvalAgent(eval_scorer, query_tracer),
    )


def get_query_executor(
    orchestration: QueryOrchestrationService = Depends(get_query_orchestration),
    graph_runner: QueryGraphRunner = Depends(get_query_graph_runner),
) -> QueryExecutor:
    return QueryExecutor(graph_runner, orchestration)


def get_stream_query_executor(
    session: AsyncSession = Depends(get_db_session),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    refrag_context_builder: HeuristicRefragContextBuilder = Depends(get_refrag_context_builder),
    llm_service: StreamingLLMService = Depends(get_streaming_llm_service),
    reranker: Reranker = Depends(get_reranker),
    eval_scorer: EvalScorer = Depends(get_eval_scorer),
    query_tracer: LangfuseQueryTracer = Depends(get_query_tracer),
    orchestration: QueryOrchestrationService = Depends(get_query_orchestration),
) -> StreamQueryExecutor:
    retrieval_service = HybridRetrievalService(ChunkRepository.from_session(session), embedding_provider)
    graph_runner = StreamingQueryGraphRunner(
        ConversationContextAgent(),
        RouterAgent(),
        RetrievalAgent(retrieval_service, reranker),
        RefragContextAgent(refrag_context_builder),
        StreamingSynthesisAgent(llm_service),
        EvalAgent(eval_scorer, query_tracer),
    )
    return StreamQueryExecutor(graph_runner, orchestration)
