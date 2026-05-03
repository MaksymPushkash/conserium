from dishka import Provider, Scope, provide

from src.application.ports.ai.embedding_provider import IEmbeddingProvider
from src.application.ports.ai.llm_service import ILLMService, IStreamingLLMService
from src.application.ports.cache.cache import ICache
from src.application.ports.refrag.refrag_context_builder import IRefragContextBuilder
from src.application.services.refrag.heuristic_context_builder import HeuristicRefragContextBuilder
from src.infrastructure.ai.providers.cached_embedding_provider import CachedEmbeddingProvider
from src.infrastructure.ai.providers.openai_embedding_provider import OpenAIEmbeddingProvider
from src.infrastructure.ai.providers.openai_llm_service import OpenAILLMService


class AIProvider(Provider):
    @provide(scope=Scope.APP)
    def get_embedding_provider(self, cache: ICache) -> IEmbeddingProvider:
        return CachedEmbeddingProvider(OpenAIEmbeddingProvider(), cache)

    @provide(scope=Scope.APP)
    def get_llm_service(self) -> ILLMService:
        return OpenAILLMService()

    @provide(scope=Scope.APP)
    def get_streaming_llm_service(self) -> IStreamingLLMService:
        return OpenAILLMService()

    @provide(scope=Scope.APP)
    def get_refrag_context_builder(self) -> IRefragContextBuilder:
        return HeuristicRefragContextBuilder()
