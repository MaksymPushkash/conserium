from __future__ import annotations

import json
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog
from fastapi import Depends

from src.chats.repository import ChatRepository
from src.collections.repository import CollectionRepository
from src.documents.activity_repository import DocumentActivityRepository
from src.documents.chunk_repository import ChunkRepository
from src.kit.ai.providers.cached_embedding_provider import CachedEmbeddingProvider
from src.kit.ai.providers.openai_embedding_provider import OpenAIEmbeddingProvider
from src.kit.ai.providers.openai_llm_service import OpenAILLMService
from src.kit.cache.redis import get_redis
from src.kit.cache.redis_cache import RedisCache
from src.kit.cache.redis_conversation_store import RedisConversationStore
from src.kit.exceptions import QueryProcessingException, QueryValidationException
from src.observability.langfuse_tracer import LangfuseQueryTracer
from src.postgres import AsyncSession, get_db_session
from src.query.agents.conversation_context_agent import ConversationContextAgent
from src.query.agents.eval_agent import EvalAgent
from src.query.agents.graph_runner import QueryGraphRunner
from src.query.agents.refrag_context_agent import RefragContextAgent
from src.query.agents.retrieval_agent import RetrievalAgent
from src.query.agents.router_agent import RouterAgent
from src.query.agents.state import ConseriumQueryState
from src.query.agents.streaming_graph_runner import StreamingQueryGraphRunner
from src.query.agents.streaming_synthesis_agent import StreamingSynthesisAgent
from src.query.agents.synthesis_agent import SynthesisAgent
from src.query.repository import SearchQueryRepository
from src.query.schemas import (
    QueryDebugDTO,
    QueryDebugResponse,
    QueryDTO,
    QueryRequest,
    QueryResponse,
    QueryResultDTO,
    QuerySourceDTO,
    QuerySourceResponse,
    QueryStreamEventDTO,
    QueryStreamEventType,
    RefragChunk,
    RefragChunkResponse,
    RefragContextPackage,
    RefragContextResponse,
)
from src.query.services.evaluation.heuristic_ragas_scorer import HeuristicRagasScorer
from src.query.services.evaluation.ragas_eval_scorer import RagasEvalScorer
from src.query.services.query.conversation import QueryConversationService
from src.query.services.query.orchestration import QueryOrchestrationService
from src.query.services.query.payloads import (
    build_follow_up_questions,
    mark_sources_used_in_answer,
    query_debug,
    query_debug_payload,
    refrag_context_payload,
    stream_metadata_payload,
    stream_refrag_context_payload,
    stream_sources_payload,
)
from src.query.services.query.persistence import QueryPersistenceService
from src.query.services.refrag.heuristic_context_builder import HeuristicRefragContextBuilder
from src.query.services.retrieval.cross_encoder_reranker import CrossEncoderReranker
from src.query.services.retrieval.embedding_reranker import EmbeddingReranker
from src.query.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from src.settings import settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from redis.asyncio import Redis

    from src.kit.ports.ai.embedding_provider import IEmbeddingProvider
    from src.kit.ports.ai.llm_service import ILLMService, IStreamingLLMService
    from src.kit.ports.ai.reranker import IReranker
    from src.kit.ports.cache.cache import ICache
    from src.kit.ports.conversations.conversation_store import IConversationStore
    from src.kit.ports.evaluation.eval_scorer import IEvalScorer
    from src.kit.ports.observability.query_trace import IQueryTracer
    from src.kit.ports.refrag.refrag_context_builder import IRefragContextBuilder
    from src.models.user import UserModel

logger = structlog.get_logger(__name__)


class QueryExecutor:
    RECENT_TURN_LIMIT = 6

    def __init__(
        self,
        graph_runner: QueryGraphRunner,
        orchestration: QueryOrchestrationService,
    ) -> None:
        self._graph_runner = graph_runner
        self._orchestration = orchestration

    async def __call__(self, dto: QueryDTO) -> QueryResultDTO:
        query = dto.query.strip()
        if not query:
            raise QueryValidationException("query cannot be empty")

        conversation_id = dto.conversation_id or uuid4()
        conversation_turns = await self._orchestration.prepare_context(dto, query=query, conversation_id=conversation_id)
        started_at = perf_counter()
        state = await self._graph_runner.run(
            ConseriumQueryState(
                query=query,
                user_id=dto.user_id,
                limit=dto.limit,
                conversation_id=conversation_id,
                collection_id=dto.collection_id,
                tag_names=dto.tag_names,
                document_types=dto.document_types,
                document_ids=dto.document_ids,
                conversation_turns=conversation_turns,
                retrieval_query=dto.retrieval_query.strip() if dto.retrieval_query is not None else None,
                relevance_query=dto.relevance_query.strip() if dto.relevance_query is not None else None,
                answer_language=dto.answer_language,
                retrieval_depth=dto.retrieval_depth,
            )
        )
        latency_ms = int((perf_counter() - started_at) * 1000)
        if state.refrag_context is None:
            raise QueryProcessingException("query graph did not produce refrag_context")
        state.sources = mark_sources_used_in_answer(state.sources, state.answer)
        debug = query_debug(query, state)
        follow_up_questions = build_follow_up_questions(state.answer, state.sources)
        await self._orchestration.append_turn(
            user_id=dto.user_id,
            conversation_id=conversation_id,
            query=query,
            answer=state.answer,
            sources=state.sources,
        )
        await self._orchestration.record_interaction(
            dto,
            query=query,
            state=state,
            latency_ms=latency_ms,
            conversation_id=conversation_id,
            refrag_context=refrag_context_payload(state.refrag_context),
        )
        logger.info(
            "query_completed",
            mode="sync",
            trace_id=state.trace_id,
            conversation_id=str(conversation_id),
            collection_id=str(dto.collection_id) if dto.collection_id else None,
            sources=len(state.sources),
            used_sources=sum(1 for source in state.sources if source.used_in_answer),
            latency_ms=latency_ms,
        )
        return QueryResultDTO(
            conversation_id=conversation_id,
            query=query,
            answer=state.answer,
            sources=state.sources,
            refrag_context=state.refrag_context,
            debug=debug,
            suggested_follow_up_questions=follow_up_questions,
        )


class StreamQueryExecutor:
    RECENT_TURN_LIMIT = 6

    def __init__(
        self,
        graph_runner: StreamingQueryGraphRunner,
        orchestration: QueryOrchestrationService,
    ) -> None:
        self._graph_runner = graph_runner
        self._orchestration = orchestration

    async def __call__(self, dto: QueryDTO) -> AsyncIterator[QueryStreamEventDTO]:
        query = dto.query.strip()
        if not query:
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.ERROR,
                data={"message": "query cannot be empty"},
            )
            return

        query_id = uuid4()
        conversation_id = dto.conversation_id or uuid4()
        started_at = perf_counter()
        try:
            conversation_turns = await self._orchestration.prepare_context(dto, query=query, conversation_id=conversation_id)
            state = await self._graph_runner.prepare(
                ConseriumQueryState(
                    query=query,
                    user_id=dto.user_id,
                    limit=dto.limit,
                    conversation_id=conversation_id,
                    collection_id=dto.collection_id,
                    tag_names=dto.tag_names,
                    document_types=dto.document_types,
                    document_ids=dto.document_ids,
                    conversation_turns=conversation_turns,
                    retrieval_query=dto.retrieval_query.strip() if dto.retrieval_query is not None else None,
                    relevance_query=dto.relevance_query.strip() if dto.relevance_query is not None else None,
                    answer_language=dto.answer_language,
                    retrieval_depth=dto.retrieval_depth,
                )
            )
            if state.refrag_context is None:
                raise QueryProcessingException("query graph did not produce refrag_context")

            yield QueryStreamEventDTO(
                event=QueryStreamEventType.METADATA,
                data=stream_metadata_payload(query_id, conversation_id, query, state.sources),
            )

            answer_parts: list[str] = []
            async for token in self._graph_runner.stream_answer(state):
                if token:
                    answer_parts.append(token)
                    yield QueryStreamEventDTO(
                        event=QueryStreamEventType.TOKEN,
                        data={"text": token},
                    )

            state.answer = "".join(answer_parts)
            state.sources = mark_sources_used_in_answer(state.sources, state.answer)
            follow_up_questions = build_follow_up_questions(state.answer, state.sources)
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.DEBUG,
                data=query_debug_payload(query, state),
            )
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.SOURCES,
                data=stream_sources_payload(state.sources),
            )
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.REFRAG_CONTEXT,
                data=stream_refrag_context_payload(state.refrag_context),
            )
            await self._orchestration.append_turn(
                user_id=dto.user_id,
                conversation_id=conversation_id,
                query=query,
                answer=state.answer,
                sources=state.sources,
            )
            state = await self._graph_runner.evaluate(state)
            latency_ms = int((perf_counter() - started_at) * 1000)
            if state.refrag_context is None:
                raise QueryProcessingException("query graph did not produce refrag_context")
            await self._orchestration.record_interaction(
                dto,
                query=query,
                state=state,
                latency_ms=latency_ms,
                conversation_id=conversation_id,
                refrag_context=refrag_context_payload(state.refrag_context),
            )
            logger.info(
                "query_completed",
                mode="stream",
                trace_id=state.trace_id,
                conversation_id=str(conversation_id),
                collection_id=str(dto.collection_id) if dto.collection_id else None,
                sources=len(state.sources),
                used_sources=sum(1 for source in state.sources if source.used_in_answer),
                latency_ms=latency_ms,
            )
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.DONE,
                data={
                    "query_id": str(query_id),
                    "conversation_id": str(conversation_id),
                    "eval_scores": state.eval_scores,
                    "trace_id": state.trace_id,
                    "suggested_follow_up_questions": follow_up_questions,
                },
            )
        except Exception as exc:
            yield QueryStreamEventDTO(
                event=QueryStreamEventType.ERROR,
                data={"query_id": str(query_id), "conversation_id": str(conversation_id), "message": str(exc)},
            )


def get_cache(redis: Redis = Depends(get_redis)) -> ICache:
    return RedisCache(redis)


def get_conversation_store(cache: ICache = Depends(get_cache)) -> IConversationStore:
    return RedisConversationStore(cache)


def get_query_orchestration(
    session: AsyncSession = Depends(get_db_session),
    conversation_store: IConversationStore = Depends(get_conversation_store),
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


def get_embedding_provider(cache: ICache = Depends(get_cache)) -> IEmbeddingProvider:
    return CachedEmbeddingProvider(OpenAIEmbeddingProvider(), cache)


def get_llm_service() -> ILLMService:
    return OpenAILLMService()


def get_streaming_llm_service() -> IStreamingLLMService:
    return OpenAILLMService()


def get_refrag_context_builder() -> IRefragContextBuilder:
    return HeuristicRefragContextBuilder()


def get_reranker(embedding_provider: IEmbeddingProvider = Depends(get_embedding_provider)) -> IReranker:
    fallback = EmbeddingReranker(embedding_provider)
    if settings.RERANKER_BACKEND.lower() in {"cross_encoder", "cross-encoder"}:
        return CrossEncoderReranker(fallback=fallback)
    return fallback


def get_eval_scorer() -> IEvalScorer:
    fallback = HeuristicRagasScorer()
    if settings.EVAL_SCORER.lower() == "ragas":
        return RagasEvalScorer(fallback=fallback)
    return fallback


def get_query_tracer() -> IQueryTracer:
    return LangfuseQueryTracer()


def get_query_graph_runner(
    session: AsyncSession = Depends(get_db_session),
    embedding_provider: IEmbeddingProvider = Depends(get_embedding_provider),
    refrag_context_builder: IRefragContextBuilder = Depends(get_refrag_context_builder),
    llm_service: ILLMService = Depends(get_llm_service),
    reranker: IReranker = Depends(get_reranker),
    eval_scorer: IEvalScorer = Depends(get_eval_scorer),
    query_tracer: IQueryTracer = Depends(get_query_tracer),
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
    embedding_provider: IEmbeddingProvider = Depends(get_embedding_provider),
    refrag_context_builder: IRefragContextBuilder = Depends(get_refrag_context_builder),
    llm_service: IStreamingLLMService = Depends(get_streaming_llm_service),
    reranker: IReranker = Depends(get_reranker),
    eval_scorer: IEvalScorer = Depends(get_eval_scorer),
    query_tracer: IQueryTracer = Depends(get_query_tracer),
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


def to_query_dto(body: QueryRequest, current_user: UserModel) -> QueryDTO:
    tag_names = tuple(tag.strip().lower() for tag in body.tag_names or [] if tag.strip())
    ai_preferences = _ai_preferences(current_user.preferences)
    retrieval_depth = _retrieval_depth(ai_preferences)
    return QueryDTO(
        user_id=current_user.id,
        query=body.query,
        conversation_id=body.conversation_id,
        collection_id=body.collection_id,
        tag_names=tag_names or None,
        document_types=tuple(body.document_types) if body.document_types else None,
        document_ids=(body.document_id,) if body.document_id else None,
        limit=_query_limit(body.limit, retrieval_depth),
        answer_language=_answer_language(ai_preferences),
        retrieval_depth=retrieval_depth,
    )


def to_query_response(dto: QueryResultDTO) -> QueryResponse:
    return QueryResponse(
        conversation_id=dto.conversation_id,
        query=dto.query,
        answer=dto.answer,
        sources=[to_query_source_response(source, index) for index, source in enumerate(dto.sources, start=1)],
        refrag_context=to_refrag_context_response(dto.refrag_context),
        debug=to_query_debug_response(dto.debug) if dto.debug else None,
        suggested_follow_up_questions=dto.suggested_follow_up_questions,
    )


def to_query_source_response(dto: QuerySourceDTO, index: int) -> QuerySourceResponse:
    return QuerySourceResponse(
        chunk_id=dto.chunk_id,
        document_id=dto.document_id,
        document_title=dto.document_title,
        content=dto.content,
        page_number=dto.page_number,
        chunk_index=dto.chunk_index,
        score=dto.score,
        citation=f"[{index}]",
        used_in_answer=dto.used_in_answer,
    )


def to_refrag_chunk_response(dto: RefragChunk, citation: str | None) -> RefragChunkResponse:
    return RefragChunkResponse(
        chunk_id=dto.chunk_id,
        document_id=dto.document_id,
        document_title=dto.document_title,
        representation=dto.representation,
        page_number=dto.page_number,
        chunk_index=dto.chunk_index,
        score=dto.score,
        context_text=dto.context_text,
        original_token_count=dto.original_token_count,
        context_token_count=dto.context_token_count,
        citation=citation,
    )


def to_refrag_context_response(dto: RefragContextPackage) -> RefragContextResponse:
    full_text_chunks = [
        to_refrag_chunk_response(chunk, f"[{index}]") for index, chunk in enumerate(dto.full_text_chunks, start=1)
    ]
    compressed_start = len(dto.full_text_chunks) + 1
    compressed_chunks = [
        to_refrag_chunk_response(chunk, f"[{index}]")
        for index, chunk in enumerate(dto.compressed_chunks, start=compressed_start)
    ]
    discarded_chunks = [to_refrag_chunk_response(chunk, None) for chunk in dto.discarded_chunks]
    return RefragContextResponse(
        full_text_chunks=full_text_chunks,
        compressed_chunks=compressed_chunks,
        discarded_chunks=discarded_chunks,
        total_original_tokens=dto.total_original_tokens,
        total_context_tokens=dto.total_context_tokens,
        compression_strategy=dto.compression_strategy,
    )


def to_query_debug_response(dto: QueryDebugDTO) -> QueryDebugResponse:
    return QueryDebugResponse(
        original_query=dto.original_query,
        retrieval_query=dto.retrieval_query,
        selected_collection_id=dto.selected_collection_id,
        selected_tags=dto.selected_tags,
        promoted_document_ids=dto.promoted_document_ids,
        retrieved_sources=[
            to_query_source_response(source, index) for index, source in enumerate(dto.retrieved_sources, start=1)
        ],
        final_sources=[to_query_source_response(source, index) for index, source in enumerate(dto.final_sources, start=1)],
        used_sources=[to_query_source_response(source, index) for index, source in enumerate(dto.used_sources, start=1)],
        filtered_sources=[
            to_query_source_response(source, index) for index, source in enumerate(dto.filtered_sources, start=1)
        ],
    )


def format_sse_event(dto: QueryStreamEventDTO) -> str:
    payload = json.dumps(dto.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {dto.event.value}\ndata: {payload}\n\n"


def _ai_preferences(preferences: dict[str, object]) -> dict[str, object]:
    ai = preferences.get("ai")
    return ai if isinstance(ai, dict) else {}


def _answer_language(ai_preferences: dict[str, object]) -> str:
    value = ai_preferences.get("answer_language")
    return value if value in {"match_question", "english", "ukrainian"} else "match_question"


def _retrieval_depth(ai_preferences: dict[str, object]) -> str:
    value = ai_preferences.get("retrieval_depth")
    return value if value in {"focused", "balanced", "broad"} else "balanced"


def _query_limit(request_limit: int, retrieval_depth: str) -> int:
    if retrieval_depth == "focused":
        return min(request_limit, 5)
    if retrieval_depth == "broad":
        return max(request_limit, 12)
    return request_limit




__all__ = [
    "QueryExecutor",
    "StreamQueryExecutor",
    "format_sse_event",
    "get_query_executor",
    "get_stream_query_executor",
    "to_query_dto",
    "to_query_response",
]
