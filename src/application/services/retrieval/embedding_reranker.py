from __future__ import annotations

from math import sqrt
from typing import TYPE_CHECKING

from src.application.ports.ai.reranker import IReranker
from src.core.metrics import metrics_registry

if TYPE_CHECKING:
    from src.application.dtos.query_dtos import QuerySourceDTO
    from src.application.ports.ai.embedding_provider import IEmbeddingProvider


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class EmbeddingReranker(IReranker):
    def __init__(self, embedding_provider: IEmbeddingProvider) -> None:
        self._emb = embedding_provider

    async def rerank(self, query: str, candidates: list[QuerySourceDTO], top_k: int) -> list[QuerySourceDTO]:
        if not candidates:
            return []

        query_emb = await self._emb.embed_text(query)
        contents = [c.content for c in candidates]
        candidate_embs = await self._emb.embed_texts(contents)

        scored = []
        for cand, emb in zip(candidates, candidate_embs, strict=True):
            score = _cosine(query_emb, emb)
            scored.append((score, cand))

        scored.sort(key=lambda s: s[0], reverse=True)
        metrics_registry.inc_counter(
            "conserium_reranker_events_total",
            "Reranker execution events.",
            labels={"backend": "embedding", "status": "success"},
        )
        top = [item[1] for item in scored[:top_k]]
        return top
