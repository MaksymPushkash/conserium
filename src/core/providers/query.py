from dishka import Provider, Scope, provide

from src.application.agents.query.conversation_context_agent import ConversationContextAgent
from src.application.agents.query.eval_agent import EvalAgent
from src.application.agents.query.graph_runner import QueryGraphRunner
from src.application.agents.query.refrag_context_agent import RefragContextAgent
from src.application.agents.query.retrieval_agent import RetrievalAgent
from src.application.agents.query.router_agent import RouterAgent
from src.application.agents.query.streaming_graph_runner import StreamingQueryGraphRunner
from src.application.agents.query.streaming_synthesis_agent import StreamingSynthesisAgent
from src.application.agents.query.synthesis_agent import SynthesisAgent
from src.application.ports.ai.embedding_provider import IEmbeddingProvider
from src.application.ports.ai.llm_service import ILLMService, IStreamingLLMService
from src.application.ports.ai.reranker import IReranker
from src.application.ports.conversations.conversation_store import IConversationStore
from src.application.ports.evaluation.eval_scorer import IEvalScorer
from src.application.ports.observability.query_trace import IQueryTracer
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.ports.refrag.refrag_context_builder import IRefragContextBuilder
from src.application.services.evaluation.heuristic_ragas_scorer import HeuristicRagasScorer
from src.application.services.evaluation.ragas_eval_scorer import RagasEvalScorer
from src.application.services.retrieval.cross_encoder_reranker import CrossEncoderReranker
from src.application.services.retrieval.embedding_reranker import EmbeddingReranker
from src.application.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from src.application.use_cases.query.chat_use_cases import (
    CreateChatUseCase,
    DeleteChatUseCase,
    GetChatUseCase,
    ListChatsUseCase,
    RenameChatUseCase,
)
from src.application.use_cases.query.query_use_case import QueryUseCase
from src.application.use_cases.query.stream_query_use_case import StreamQueryUseCase
from src.core.config import settings
from src.infrastructure.observability.langfuse_tracer import LangfuseQueryTracer


class QueryProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_create_chat_use_case(self, uow: IUnitOfWork) -> CreateChatUseCase:
        return CreateChatUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_list_chats_use_case(self, uow: IUnitOfWork) -> ListChatsUseCase:
        return ListChatsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_get_chat_use_case(self, uow: IUnitOfWork) -> GetChatUseCase:
        return GetChatUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_rename_chat_use_case(self, uow: IUnitOfWork) -> RenameChatUseCase:
        return RenameChatUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_delete_chat_use_case(self, uow: IUnitOfWork) -> DeleteChatUseCase:
        return DeleteChatUseCase(uow)

    @provide(scope=Scope.APP)
    def get_reranker(self, embedding_provider: IEmbeddingProvider) -> IReranker:
        fallback = EmbeddingReranker(embedding_provider)
        return CrossEncoderReranker(fallback=fallback)

    @provide(scope=Scope.APP)
    def get_eval_scorer(self) -> IEvalScorer:
        fallback = HeuristicRagasScorer()
        if settings.EVAL_SCORER.lower() == "ragas":
            return RagasEvalScorer(fallback=fallback)
        return fallback

    @provide(scope=Scope.APP)
    def get_query_tracer(self) -> IQueryTracer:
        return LangfuseQueryTracer()

    @provide(scope=Scope.REQUEST)
    def get_query_use_case(
        self,
        uow: IUnitOfWork,
        embedding_provider: IEmbeddingProvider,
        refrag_context_builder: IRefragContextBuilder,
        llm_service: ILLMService,
        conversation_store: IConversationStore,
        reranker: IReranker,
        eval_scorer: IEvalScorer,
        query_tracer: IQueryTracer,
    ) -> QueryUseCase:
        retrieval_service = HybridRetrievalService(uow, embedding_provider)
        graph_runner = QueryGraphRunner(
            ConversationContextAgent(),
            RouterAgent(),
            RetrievalAgent(retrieval_service, reranker),
            RefragContextAgent(refrag_context_builder),
            SynthesisAgent(llm_service),
            EvalAgent(eval_scorer, query_tracer),
        )
        return QueryUseCase(graph_runner, conversation_store, uow)

    @provide(scope=Scope.REQUEST)
    def get_stream_query_use_case(
        self,
        uow: IUnitOfWork,
        embedding_provider: IEmbeddingProvider,
        refrag_context_builder: IRefragContextBuilder,
        llm_service: IStreamingLLMService,
        conversation_store: IConversationStore,
        reranker: IReranker,
        eval_scorer: IEvalScorer,
        query_tracer: IQueryTracer,
    ) -> StreamQueryUseCase:
        retrieval_service = HybridRetrievalService(uow, embedding_provider)
        graph_runner = StreamingQueryGraphRunner(
            ConversationContextAgent(),
            RouterAgent(),
            RetrievalAgent(retrieval_service, reranker),
            RefragContextAgent(refrag_context_builder),
            StreamingSynthesisAgent(llm_service),
            EvalAgent(eval_scorer, query_tracer),
        )
        return StreamQueryUseCase(graph_runner, conversation_store, uow)
