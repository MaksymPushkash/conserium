from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import uuid
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.application.dtos.refrag_dtos import RefragChunk, RefragContextPackage, RefragRepresentation
from src.application.services.evaluation.heuristic_ragas_scorer import HeuristicRagasScorer

_ZERO_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")


async def _score_offline_case(case: dict[str, Any]) -> dict[str, object]:
    chunk = RefragChunk(
        chunk_id=_ZERO_UUID,
        document_id=_ZERO_UUID,
        document_title="Synthetic Eval",
        original_text=str(case["context"]),
        context_text=str(case["context"]),
        representation=RefragRepresentation.FULL_TEXT,
        page_number=None,
        chunk_index=0,
        score=1.0,
        original_token_count=len(str(case["context"]).split()),
        context_token_count=len(str(case["context"]).split()),
    )
    context = RefragContextPackage(
        query=str(case["query"]),
        full_text_chunks=[chunk],
        compressed_chunks=[],
        discarded_chunks=[],
        total_original_tokens=chunk.original_token_count,
        total_context_tokens=chunk.context_token_count,
        compression_strategy="offline_eval",
    )
    scores = await HeuristicRagasScorer().score(
        query=str(case["query"]),
        answer=str(case["answer"]),
        context=context,
    )
    expected_terms = [str(term).lower() for term in case.get("expected_answer_terms", [])]
    answer = str(case["answer"]).lower()
    source_context = str(case["context"]).lower()
    if expected_terms:
        scores["answer_relevancy"] = round(
            sum(1 for term in expected_terms if term in answer) / len(expected_terms),
            4,
        )
        scores["context_recall"] = round(
            sum(1 for term in expected_terms if term in source_context) / len(expected_terms),
            4,
        )
        supported_expected_terms = sum(1 for term in expected_terms if term in answer and term in source_context)
        scores["faithfulness"] = round(supported_expected_terms / len(expected_terms), 4)
    return {"id": case["id"], "scores": scores}


def _score_api_case(base_url: str, token: str, case: dict[str, Any]) -> dict[str, object]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/query",
        data=json.dumps({"query": case["query"], "limit": 5}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))

    answer = str(payload.get("answer", ""))
    expected_terms = [str(term).lower() for term in case.get("expected_answer_terms", [])]
    hits = sum(1 for term in expected_terms if term in answer.lower())
    answer_relevancy = round(hits / max(len(expected_terms), 1), 4)
    return {
        "id": case["id"],
        "scores": {
            "faithfulness": 1.0 if payload.get("sources") else 0.0,
            "answer_relevancy": answer_relevancy,
            "context_recall": 1.0 if payload.get("sources") else 0.0,
        },
    }


def _summarize(results: list[dict[str, object]]) -> dict[str, float]:
    score_keys = ["faithfulness", "answer_relevancy", "context_recall"]
    summary: dict[str, float] = {}
    for key in score_keys:
        values = [float(result["scores"][key]) for result in results]  # type: ignore[index]
        summary[key] = round(sum(values) / max(len(values), 1), 4)
    return summary


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", json.loads(path.read_text(encoding="utf-8")))


def _threshold_failures(summary: dict[str, float], thresholds: dict[str, float]) -> list[str]:
    failures: list[str] = []
    for key, minimum in thresholds.items():
        value = summary[key]
        if value < minimum:
            failures.append(f"{key}: {value:.4f} < required {minimum:.4f}")
    return failures


def _print_threshold_report(summary: dict[str, float], thresholds: dict[str, float]) -> None:
    print("Eval threshold report:", file=sys.stderr)
    for key, minimum in thresholds.items():
        value = summary[key]
        status = "PASS" if value >= minimum else "FAIL"
        print(f"- {status} {key}: {value:.4f} / required {minimum:.4f}", file=sys.stderr)


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Run Cortex query eval regression.")
    parser.add_argument("--dataset", default="evals/query_eval_set.json")
    parser.add_argument("--min-faithfulness", type=float, default=0.8)
    parser.add_argument("--min-answer-relevancy", type=float, default=0.6)
    parser.add_argument("--min-context-recall", type=float, default=0.6)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--output", default="", help="Optional path to write the JSON eval report.")
    args = parser.parse_args()

    cases = _load_cases(Path(args.dataset))
    if args.base_url and args.token:
        results = [_score_api_case(args.base_url, args.token, case) for case in cases]
    else:
        import asyncio

        results = await asyncio.gather(*[_score_offline_case(case) for case in cases])

    summary = _summarize(results)
    output = {"summary": summary, "results": results}
    rendered_output = json.dumps(output, indent=2, sort_keys=True)
    print(rendered_output)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered_output + "\n", encoding="utf-8")

    thresholds = {
        "faithfulness": args.min_faithfulness,
        "answer_relevancy": args.min_answer_relevancy,
        "context_recall": args.min_context_recall,
    }
    _print_threshold_report(summary, thresholds)
    failures = _threshold_failures(summary, thresholds)
    if failures:
        print("Eval regression failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(_main()))
