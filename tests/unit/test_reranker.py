import uuid
from typing import Any

import pytest

from src.application.dtos.query_dtos import QuerySourceDTO
from src.application.ports.ai.embedding_provider import IEmbeddingProvider
from src.application.ports.ai.reranker import IReranker
from src.application.services.retrieval.cross_encoder_reranker import CrossEncoderReranker
from src.application.services.retrieval.embedding_reranker import EmbeddingReranker
from src.core.providers.query import QueryProvider


class _FailingLoadCrossEncoderReranker(CrossEncoderReranker):
    def _get_model(self) -> Any:
        raise RuntimeError("model unavailable")


class _FallbackReranker(IReranker):
    def __init__(self) -> None:
        self.called = False

    async def rerank(self, query: str, candidates: list[QuerySourceDTO], top_k: int) -> list[QuerySourceDTO]:
        self.called = True
        return list(reversed(candidates))[:top_k]


class _FakeEmbeddingProvider(IEmbeddingProvider):
    async def embed_text(self, text: str) -> list[float]:
        return [0.1] * 1536

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1536 for _ in texts]


def _source(index: int) -> QuerySourceDTO:
    return QuerySourceDTO(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=f"Doc {index}",
        content=f"Candidate {index}",
        page_number=None,
        chunk_index=index,
        score=None,
    )


@pytest.mark.asyncio
async def test_cross_encoder_reranker_falls_back_when_model_load_fails() -> None:
    fallback = _FallbackReranker()
    reranker = _FailingLoadCrossEncoderReranker(fallback=fallback)
    first = _source(1)
    second = _source(2)

    result = await reranker.rerank("query", [first, second], top_k=2)

    assert fallback.called is True
    assert result == [second, first]


def test_query_provider_uses_embedding_reranker_by_default() -> None:
    provider = QueryProvider()

    reranker = provider.get_reranker(_FakeEmbeddingProvider())

    assert isinstance(reranker, EmbeddingReranker)
