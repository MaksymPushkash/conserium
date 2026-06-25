from openai import AsyncOpenAI

from src.kit.ai.embedding_provider import EmbeddingProvider
from src.models.chunk import ChunkModel
from src.observability.metrics_registry import metrics_registry
from src.settings import settings


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        if settings.OPENAI_EMBEDDING_DIMENSIONS != ChunkModel.EMBEDDING_DIMENSIONS:
            raise ValueError(
                "OPENAI_EMBEDDING_DIMENSIONS must match "
                f"ChunkModel.EMBEDDING_DIMENSIONS ({ChunkModel.EMBEDDING_DIMENSIONS})"
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
            self._client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                timeout=settings.OPENAI_REQUEST_TIMEOUT_SECONDS,
                max_retries=settings.OPENAI_MAX_RETRIES,
            )
        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=texts,
                dimensions=ChunkModel.EMBEDDING_DIMENSIONS,
            )
        except Exception:
            metrics_registry.inc_counter(
                "conserium_openai_requests_total",
                "OpenAI API requests grouped by operation and outcome.",
                labels={"operation": "embeddings", "status": "error"},
            )
            raise
        metrics_registry.inc_counter(
            "conserium_openai_requests_total",
            "OpenAI API requests grouped by operation and outcome.",
            labels={"operation": "embeddings", "status": "success"},
        )
        metrics_registry.inc_counter(
            "conserium_openai_estimated_cost_usd",
            "Approximate OpenAI API cost estimate in USD.",
            value=_estimate_embedding_cost(texts),
        )
        return [list(item.embedding) for item in response.data]

    async def aclose(self) -> None:
        if self._client is None:
            return
        client = self._client
        self._client = None
        await client.close()


def _estimate_embedding_cost(texts: list[str]) -> float:
    estimated_tokens = max(1, sum(len(text.split()) for text in texts))
    return estimated_tokens / 1000 * 0.00002
