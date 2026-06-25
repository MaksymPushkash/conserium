from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.observability.metrics_registry import metrics_registry

if TYPE_CHECKING:
    from src.observability.langfuse_tracer import LangfuseQueryTracer
    from src.query.agents.state import ConseriumQueryState
    from src.query.services.evaluation.scorer import EvalScorer

logger = logging.getLogger(__name__)


class EvalAgent:
    def __init__(self, eval_scorer: EvalScorer, query_tracer: LangfuseQueryTracer | None = None) -> None:
        self._eval_scorer = eval_scorer
        self._query_tracer = query_tracer

    async def evaluate(self, state: ConseriumQueryState) -> ConseriumQueryState:
        if state.refrag_context is None:
            raise ValueError("refrag_context is required before evaluation")

        try:
            state.eval_scores = await self._eval_scorer.score(
                query=state.query,
                answer=state.answer,
                context=state.refrag_context,
            )
            for score_name, score_value in state.eval_scores.items():
                metrics_registry.observe_histogram(
                    "conserium_query_eval_score",
                    "Query evaluation score values.",
                    labels={"score": score_name, "query_type": state.query_type.value},
                    value=score_value,
                )
        except Exception as exc:
            logger.warning("query evaluation failed", exc_info=exc)
            state.eval_scores = {}

        if self._query_tracer is not None:
            try:
                state.trace_id = await self._query_tracer.trace_query(state)
            except Exception as exc:
                logger.warning("query tracing failed", exc_info=exc)
        return state
