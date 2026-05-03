from __future__ import annotations

import logging
from time import perf_counter
from typing import TYPE_CHECKING, Any

from src.application.ports.ai.reranker import IReranker
from src.core.metrics import metrics_registry

if TYPE_CHECKING:
    from src.application.dtos.query_dtos import QuerySourceDTO

logger = logging.getLogger(__name__)


class CrossEncoderReranker(IReranker):
    """A cross-encoder reranker using sentence-transformers.
    
    This provides true second-stage reranking by scoring query-document
    pairs jointly through a cross-attention transformer.
    """

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

        # Prepare pairs: (query, document_text)
        pairs = [[query, source.content] for source in sources]

        # Score pairs
        try:
            import asyncio

            model = self._get_model()
            loop = asyncio.get_running_loop()
            started_at = perf_counter()
            # Predict can be CPU-heavy depending on the model, run in executor
            scores = await loop.run_in_executor(None, model.predict, pairs)
            metrics_registry.observe_histogram(
                "cortex_reranker_latency_seconds",
                "Reranker latency in seconds.",
                labels={"backend": "cross_encoder"},
                value=perf_counter() - started_at,
            )
            metrics_registry.inc_counter(
                "cortex_reranker_events_total",
                "Reranker execution events.",
                labels={"backend": "cross_encoder", "status": "success"},
            )

            # Attach scores to a list of tuples (score, source)
            scored_sources = list(zip(scores, sources, strict=True))

            # Sort descending by score
            scored_sources.sort(key=lambda x: x[0], reverse=True)

            # Return top_k
            return [source for _, source in scored_sources[:top_k]]

        except Exception as e:
            logger.exception("Failed to rerank sources with CrossEncoder", exc_info=e)
            metrics_registry.inc_counter(
                "cortex_reranker_events_total",
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
