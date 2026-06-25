from typing import TYPE_CHECKING, cast

from src.query.dependencies import get_eval_scorer
from src.query.services.evaluation.heuristic_ragas_scorer import HeuristicRagasScorer
from src.query.services.evaluation.ragas_eval_scorer import RagasEvalScorer
from src.settings import settings

if TYPE_CHECKING:
    from pytest import MonkeyPatch

    from src.query.schemas import RefragContextPackage
    from src.query.services.evaluation.scorer import EvalScorer


class _FallbackScorer:
    async def score(self, *, query: str, answer: str, context: object) -> dict[str, float]:
        return {"faithfulness": 0.1, "answer_relevancy": 0.2, "context_recall": 0.3}


def test_eval_scorer_dependency_uses_deterministic_scorer_by_default(monkeypatch: "MonkeyPatch") -> None:
    monkeypatch.setattr(settings, "EVAL_SCORER", "heuristic")

    scorer = get_eval_scorer()

    assert isinstance(scorer, HeuristicRagasScorer)


def test_eval_scorer_dependency_uses_ragas_adapter_when_configured(monkeypatch: "MonkeyPatch") -> None:
    monkeypatch.setattr(settings, "EVAL_SCORER", "ragas")

    scorer = get_eval_scorer()

    assert isinstance(scorer, RagasEvalScorer)


async def test_ragas_scorer_falls_back_when_external_ragas_fails(monkeypatch: "MonkeyPatch") -> None:
    scorer = RagasEvalScorer(fallback=cast("EvalScorer", _FallbackScorer()))

    def _raise(*, query: str, answer: str, context: object) -> dict[str, float]:
        raise RuntimeError("ragas unavailable")

    monkeypatch.setattr(scorer, "_score_sync", _raise)

    scores = await scorer.score(query="q", answer="a", context=cast("RefragContextPackage", object()))

    assert scores == {"faithfulness": 0.1, "answer_relevancy": 0.2, "context_recall": 0.3}
