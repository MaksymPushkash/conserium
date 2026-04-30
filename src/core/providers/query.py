from dishka import Provider, Scope, provide

from src.application.agents.query.conversation_context_agent import ConversationContextAgent
from src.application.agents.query.graph_runner import QueryGraphRunner
from src.application.agents.query.refrag_context_agent import RefragContextAgent
from src.application.agents.query.retrieval_agent import RetrievalAgent
from src.application.agents.query.router_agent import RouterAgent
from src.application.agents.query.streaming_graph_runner import StreamingQueryGraphRunner
from src.application.agents.query.streaming_synthesis_agent import StreamingSynthesisAgent
from src.application.agents.query.synthesis_agent import SynthesisAgent
from src.application.ports.ai.embedding_provider import IEmbeddingProvider
from src.application.ports.ai.llm_service import ILLMService, IStreamingLLMService
from src.application.ports.conversations.conversation_store import IConversationStore
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.ports.refrag.refrag_context_builder import IRefragContextBuilder
from src.application.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from src.application.use_cases.query.query_use_case import QueryUseCase
from src.application.use_cases.query.stream_query_use_case import StreamQueryUseCase


class QueryProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_query_use_case(
        self,
        uow: IUnitOfWork,
        embedding_provider: IEmbeddingProvider,
        refrag_context_builder: IRefragContextBuilder,
        llm_service: ILLMService,
        conversation_store: IConversationStore,
    ) -> QueryUseCase:
        retrieval_service = HybridRetrievalService(uow, embedding_provider)
        graph_runner = QueryGraphRunner(
            ConversationContextAgent(),
            RouterAgent(),
            RetrievalAgent(retrieval_service),
            RefragContextAgent(refrag_context_builder),
            SynthesisAgent(llm_service),
        )
        return QueryUseCase(graph_runner, conversation_store)

    @provide(scope=Scope.REQUEST)
    def get_stream_query_use_case(
        self,
        uow: IUnitOfWork,
        embedding_provider: IEmbeddingProvider,
        refrag_context_builder: IRefragContextBuilder,
        llm_service: IStreamingLLMService,
        conversation_store: IConversationStore,
    ) -> StreamQueryUseCase:
        retrieval_service = HybridRetrievalService(uow, embedding_provider)
        graph_runner = StreamingQueryGraphRunner(
            ConversationContextAgent(),
            RouterAgent(),
            RetrievalAgent(retrieval_service),
            RefragContextAgent(refrag_context_builder),
            StreamingSynthesisAgent(llm_service),
        )
        return StreamQueryUseCase(graph_runner, conversation_store)
