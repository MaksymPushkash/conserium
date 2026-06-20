from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import TYPE_CHECKING, Any, SupportsFloat, SupportsIndex, cast

from src.kit.ports.evaluation.eval_scorer import IEvalScorer

if TYPE_CHECKING:
    from src.query.schemas import RefragContextPackage

logger = logging.getLogger(__name__)


class RagasEvalScorer(IEvalScorer):
    def __init__(self, fallback: IEvalScorer) -> None:
        self._fallback = fallback

    async def score(
        self,
        *,
        query: str,
        answer: str,
        context: RefragContextPackage,
    ) -> dict[str, float]:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                partial(self._score_sync, query=query, answer=answer, context=context),
            )
        except Exception as exc:
            logger.warning("RAGAS scoring failed; falling back to heuristic scorer", exc_info=exc)
            return await self._fallback.score(query=query, answer=answer, context=context)

    def _score_sync(
        self,
        *,
        query: str,
        answer: str,
        context: RefragContextPackage,
    ) -> dict[str, float]:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_recall, faithfulness

        contexts = [chunk.context_text for chunk in context.selected_chunks]
        dataset = Dataset.from_dict(
            {
                "question": [query],
                "answer": [answer],
                "contexts": [contexts],
                "ground_truth": [_ground_truth_from_contexts(contexts)],
            }
        )
        result = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy, context_recall],
            raise_exceptions=False,
        )
        scores = _result_to_mapping(result)
        return {
            "faithfulness": _coerce_score(scores.get("faithfulness")),
            "answer_relevancy": _coerce_score(scores.get("answer_relevancy")),
            "context_recall": _coerce_score(scores.get("context_recall")),
        }


def _ground_truth_from_contexts(contexts: list[str]) -> str:
    return "\n\n".join(contexts[:3])


def _result_to_mapping(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_pandas"):
        frame = result.to_pandas()
        if not frame.empty:
            return dict(frame.iloc[0])
    if isinstance(result, dict):
        return result
    return {}


def _coerce_score(value: object) -> float:
    try:
        numeric_value = cast("str | SupportsFloat | SupportsIndex", value)
        return round(float(numeric_value), 4)
    except (TypeError, ValueError):
        return 0.0
