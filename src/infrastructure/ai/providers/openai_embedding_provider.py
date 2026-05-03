from openai import AsyncOpenAI

from src.application.ports.ai.embedding_provider import IEmbeddingProvider
from src.core.config import settings
from src.core.metrics import metrics_registry
from src.domain.entities.chunk_entity import ChunkEntity


class OpenAIEmbeddingProvider(IEmbeddingProvider):
    def __init__(self) -> None:
        if settings.OPENAI_EMBEDDING_DIMENSIONS != ChunkEntity.EMBEDDING_DIMENSIONS:
            raise ValueError(
                "OPENAI_EMBEDDING_DIMENSIONS must match "
                f"ChunkEntity.EMBEDDING_DIMENSIONS ({ChunkEntity.EMBEDDING_DIMENSIONS})"
            )
        self._client: AsyncOpenAI | None = None
        self._model = settings.OPENAI_EMBEDDING_MODEL

    async def embed_text(self, text: str) -> list[float]:
        embeddings = await self.embed_texts([text])
        return embeddings[0]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required to generate embeddings")
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=texts,
                dimensions=ChunkEntity.EMBEDDING_DIMENSIONS,
            )
        except Exception:
            metrics_registry.inc_counter(
                "cortex_openai_requests_total",
                "OpenAI API requests grouped by operation and outcome.",
                labels={"operation": "embeddings", "status": "error"},
            )
            raise
        metrics_registry.inc_counter(
            "cortex_openai_requests_total",
            "OpenAI API requests grouped by operation and outcome.",
            labels={"operation": "embeddings", "status": "success"},
        )
        return [list(item.embedding) for item in response.data]
