from __future__ import annotations

import logging
from time import perf_counter
from typing import TYPE_CHECKING, Any

from src.kit.ports.ai.reranker import IReranker
from src.observability.metrics_registry import metrics_registry

if TYPE_CHECKING:
    from src.query.schemas import QuerySourceDTO

logger = logging.getLogger(__name__)


class CrossEncoderReranker(IReranker):
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        fallback: IReranker | None = None,
    ) -> None:
        self._model_name = model_name
        self._fallback = fallback
        self._model: Any | None = None

    async def rerank(
        self,
        query: str,
        sources: list[QuerySourceDTO],
        top_k: int,
    ) -> list[QuerySourceDTO]:
        if not sources:
            return []
            
        if len(sources) <= 1:
            return sources[:top_k]

        pairs = [[query, source.content] for source in sources]

        try:
            import asyncio

            model = self._get_model()
            loop = asyncio.get_running_loop()
            started_at = perf_counter()

            scores = await loop.run_in_executor(None, model.predict, pairs)
            metrics_registry.observe_histogram(
                "conserium_reranker_latency_seconds",
                "Reranker latency in seconds.",
                labels={"backend": "cross_encoder"},
                value=perf_counter() - started_at,
            )
            metrics_registry.inc_counter(
                "conserium_reranker_events_total",
                "Reranker execution events.",
                labels={"backend": "cross_encoder", "status": "success"},
            )


            scored_sources = list(zip(scores, sources, strict=True))

            scored_sources.sort(key=lambda x: x[0], reverse=True)

            return [source for _, source in scored_sources[:top_k]]

        except Exception as e:
            logger.exception("Failed to rerank sources with CrossEncoder", exc_info=e)
            metrics_registry.inc_counter(
                "conserium_reranker_events_total",
                "Reranker execution events.",
                labels={"backend": "cross_encoder", "status": "error"},
            )
            if self._fallback is not None:
                return await self._fallback.rerank(query, sources, top_k)
            return sources[:top_k]

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError("sentence-transformers is required to use CrossEncoderReranker.") from exc

        logger.info("Loading CrossEncoder model: %s", self._model_name)
        self._model = CrossEncoder(self._model_name, max_length=512)
        return self._model
