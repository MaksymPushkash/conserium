from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

from src.application.ports.evaluation.eval_scorer import IEvalScorer

if TYPE_CHECKING:
    from src.application.dtos.refrag_dtos import RefragContextPackage

_WORD_RE = re.compile(r"[a-zA-Z0-9_]{3,}")


class HeuristicRagasScorer(IEvalScorer):
    async def score(
        self,
        *,
        query: str,
        answer: str,
        context: RefragContextPackage,
    ) -> dict[str, float]:
        context_text = " ".join(chunk.context_text for chunk in context.selected_chunks)
        return {
            "faithfulness": _overlap_score(answer, context_text),
            "answer_relevancy": _overlap_score(query, answer),
            "context_recall": _overlap_score(query, context_text),
        }


def _overlap_score(left: str, right: str) -> float:
    left_terms = Counter(_tokens(left))
    right_terms = Counter(_tokens(right))
    if not left_terms:
        return 0.0
    overlap = sum(min(count, right_terms[token]) for token, count in left_terms.items())
    return round(overlap / sum(left_terms.values()), 4)


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in _WORD_RE.finditer(text)]
