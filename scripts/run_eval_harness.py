from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import uuid
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.query.schemas import RefragChunk, RefragContextPackage, RefragRepresentation
from src.query.services.evaluation.heuristic_ragas_scorer import HeuristicRagasScorer
from src.query.services.retrieval.chunk_quality_filter import is_quality_chunk

_ZERO_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


async def _score_offline_case(case: dict[str, Any]) -> dict[str, object]:
    retrieved_chunks = _offline_retrieve(case)
    context = _context_from_chunks(case, retrieved_chunks)
    answer_scores = await _score_answer(case, context)
    retrieval_scores = _score_retrieval(case, retrieved_chunks)
    result = {
        "id": case["id"],
        "collection_id": case.get("collection_id"),
        "answer": answer_scores,
        "retrieval": retrieval_scores,
        "expected_sources": _expected_sources(case),
        "forbidden_sources": _forbidden_sources(case),
        "top_k_retrieved": _retrieved_artifact(retrieved_chunks),
    }
    return _apply_negative_case_scores(case, result, str(case["answer"]), retrieved_chunks)


def _score_api_case(base_url: str, token: str, case: dict[str, Any]) -> dict[str, object]:
    conversation_id = str(uuid.uuid4()) if case.get("conversation_seed_queries") else None
    for seed_query in case.get("conversation_seed_queries", []):
        _query_api(
            base_url=base_url,
            token=token,
            query=str(seed_query),
            limit=int(case.get("limit", 5)),
            collection_id=str(case["collection_id"]) if case.get("collection_id") else None,
            conversation_id=conversation_id,
        )

    payload = _query_api(
        base_url=base_url,
        token=token,
        query=str(case["query"]),
        limit=int(case.get("limit", 5)),
        collection_id=str(case["collection_id"]) if case.get("collection_id") else None,
        conversation_id=conversation_id,
    )
    sources = payload.get("sources", [])
    answer = str(payload.get("answer", ""))
    expected_terms = _expected_terms(case)
    answer_relevancy = _term_ratio(expected_terms, answer)
    source_chunks = [
        {
            "document_id": str(source.get("document_id", "")),
            "chunk_id": str(source.get("chunk_id", "")),
            "document_title": str(source.get("document_title", "")),
            "content": str(source.get("content", "")),
            "score": source.get("score"),
            "used_in_answer": source.get("used_in_answer"),
        }
        for source in sources
    ]
    result = {
        "id": case["id"],
        "collection_id": case.get("collection_id"),
        "answer": {
            "faithfulness": 1.0 if sources else 0.0,
            "answer_relevancy": answer_relevancy,
            "context_recall": 1.0 if sources else 0.0,
        },
        "retrieval": _score_retrieval(case, source_chunks),
        "expected_sources": _expected_sources(case),
        "forbidden_sources": _forbidden_sources(case),
        "top_k_retrieved": _retrieved_artifact(source_chunks),
    }
    return _apply_negative_case_scores(case, result, answer, source_chunks, require_abstention=True)


def _query_api(
    *,
    base_url: str,
    token: str,
    query: str,
    limit: int,
    collection_id: str | None,
    conversation_id: str | None,
) -> dict[str, Any]:
    request_payload: dict[str, object] = {"query": query, "limit": limit}
    if collection_id:
        request_payload["collection_id"] = collection_id
    if conversation_id:
        request_payload["conversation_id"] = conversation_id
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/query",
        data=json.dumps(request_payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return cast("dict[str, Any]", json.loads(response.read().decode("utf-8")))


def _offline_retrieve(case: dict[str, Any]) -> list[dict[str, str]]:
    chunks = [
        chunk
        for chunk in _source_chunks(case)
        if not case.get("collection_id") or chunk.get("collection_id") == str(case["collection_id"])
    ]
    query_terms = set(_terms(str(case["query"])))
    expected_terms = set(_expected_terms(case))
    scored: list[tuple[float, dict[str, str]]] = []
    for chunk in chunks:
        content = chunk["content"]
        if not is_quality_chunk(content):
            continue
        content_terms = set(_terms(content))
        lexical_hits = len(query_terms & content_terms)
        expected_hits = len(expected_terms & content_terms)
        score = lexical_hits + expected_hits * 1.5
        scored.append((score, chunk))
    ranked = sorted(scored, key=lambda item: item[0], reverse=True)
    return [chunk for score, chunk in ranked if score > 0][: int(case.get("limit", 5))]


def _context_from_chunks(case: dict[str, Any], chunks: list[dict[str, str]]) -> RefragContextPackage:
    refrag_chunks = [
        RefragChunk(
            chunk_id=_uuid_or_zero(chunk["chunk_id"]),
            document_id=_uuid_or_zero(chunk["document_id"]),
            document_title=chunk.get("document_title") or chunk["document_id"],
            original_text=chunk["content"],
            context_text=chunk["content"],
            representation=RefragRepresentation.FULL_TEXT,
            page_number=None,
            chunk_index=index,
            score=None,
            original_token_count=len(chunk["content"].split()),
            context_token_count=len(chunk["content"].split()),
        )
        for index, chunk in enumerate(chunks)
    ]
    total_tokens = sum(chunk.context_token_count for chunk in refrag_chunks)
    return RefragContextPackage(
        query=str(case["query"]),
        full_text_chunks=refrag_chunks,
        compressed_chunks=[],
        discarded_chunks=[],
        total_original_tokens=total_tokens,
        total_context_tokens=total_tokens,
        compression_strategy="offline_curated_retrieval",
    )


async def _score_answer(case: dict[str, Any], context: RefragContextPackage) -> dict[str, float]:
    scores = await HeuristicRagasScorer().score(
        query=str(case["query"]),
        answer=str(case["answer"]),
        context=context,
    )
    expected_terms = _expected_terms(case)
    answer = str(case["answer"]).lower()
    source_context = " ".join(chunk.context_text for chunk in context.selected_chunks).lower()
    if expected_terms:
        scores["answer_relevancy"] = _term_ratio(expected_terms, answer)
        scores["context_recall"] = _term_ratio(expected_terms, source_context)
        supported_terms = sum(1 for term in expected_terms if term in answer and term in source_context)
        scores["faithfulness"] = round(supported_terms / len(expected_terms), 4)
    return {key: float(value) for key, value in scores.items()}


def _score_retrieval(case: dict[str, Any], retrieved_chunks: list[dict[str, str]]) -> dict[str, float]:
    if case.get("expected_no_answer"):
        return {"hit_rate": 1.0, "source_recall": 1.0, "mrr": 1.0, "noise_rejection": _noise_rejection(case, retrieved_chunks)}

    expected_chunk_ids = {str(value) for value in case.get("expected_source_chunks", [])}
    expected_document_ids = {str(value) for value in case.get("expected_source_documents", [])}
    if not expected_chunk_ids and not expected_document_ids:
        return {
            "hit_rate": 1.0 if retrieved_chunks else 0.0,
            "source_recall": 1.0 if retrieved_chunks else 0.0,
            "mrr": 1.0 if retrieved_chunks else 0.0,
            "noise_rejection": _noise_rejection(case, retrieved_chunks),
        }

    expected = expected_chunk_ids or expected_document_ids
    retrieved_keys = [chunk["chunk_id"] if expected_chunk_ids else chunk["document_id"] for chunk in retrieved_chunks]
    matches = [key in expected for key in retrieved_keys]
    hit_rate = 1.0 if any(matches) else 0.0
    matched_expected = {key for key in retrieved_keys if key in expected}
    source_recall = round(len(matched_expected) / len(expected), 4)
    mrr = 0.0
    for rank, matched in enumerate(matches, start=1):
        if matched:
            mrr = round(1 / rank, 4)
            break
    return {"hit_rate": hit_rate, "source_recall": source_recall, "mrr": mrr, "noise_rejection": _noise_rejection(case, retrieved_chunks)}


def _expected_sources(case: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "documents": [str(value) for value in case.get("expected_source_documents", [])],
        "chunks": [str(value) for value in case.get("expected_source_chunks", [])],
    }


def _forbidden_sources(case: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "documents": [str(value) for value in case.get("forbidden_source_documents", [])],
        "chunks": [str(value) for value in case.get("forbidden_source_chunks", [])],
    }


def _noise_rejection(case: dict[str, Any], retrieved_chunks: list[dict[str, str]]) -> float:
    forbidden = _forbidden_sources(case)
    forbidden_documents = set(forbidden["documents"])
    forbidden_chunks = set(forbidden["chunks"])
    if not forbidden_documents and not forbidden_chunks:
        return 1.0
    for chunk in retrieved_chunks:
        if chunk["document_id"] in forbidden_documents or chunk["chunk_id"] in forbidden_chunks:
            return 0.0
    return 1.0


def _retrieved_artifact(retrieved_chunks: list[dict[str, Any]]) -> list[dict[str, object]]:
    return [
        {
            "rank": index,
            "document_id": chunk.get("document_id"),
            "chunk_id": chunk.get("chunk_id"),
            "document_title": chunk.get("document_title"),
            "score": chunk.get("score"),
            "used_in_answer": chunk.get("used_in_answer"),
            "content_preview": str(chunk.get("content", ""))[:240],
        }
        for index, chunk in enumerate(retrieved_chunks, start=1)
    ]


def _summarize(results: list[dict[str, object]], section: str, score_keys: list[str]) -> dict[str, float]:
    summary: dict[str, float] = {}
    for key in score_keys:
        values = [float(cast("dict[str, float]", result[section])[key]) for result in results]
        summary[key] = round(sum(values) / max(len(values), 1), 4)
    return summary


def _summarize_by_collection(
    results: list[dict[str, object]],
    section: str,
    score_keys: list[str],
) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for result in results:
        grouped.setdefault(str(result.get("collection_id") or "unscoped"), []).append(result)
    return {
        collection_id: _summarize(collection_results, section, score_keys)
        for collection_id, collection_results in sorted(grouped.items())
    }


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", json.loads(path.read_text(encoding="utf-8")))


def _load_cases_from_dir(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for dataset_path in sorted(path.glob("*.json")):
        cases.extend(_load_cases(dataset_path))
    return cases


def _threshold_failures(summary: dict[str, float], thresholds: dict[str, float]) -> list[str]:
    failures: list[str] = []
    for key, minimum in thresholds.items():
        value = summary[key]
        if value < minimum:
            failures.append(f"{key}: {value:.4f} < required {minimum:.4f}")
    return failures


def _collection_threshold_failures(
    summaries: dict[str, dict[str, float]],
    thresholds: dict[str, float],
) -> list[str]:
    failures: list[str] = []
    for collection_id, summary in summaries.items():
        for failure in _threshold_failures(summary, thresholds):
            failures.append(f"{collection_id}.{failure}")
    return failures


def _print_threshold_report(section: str, summary: dict[str, float], thresholds: dict[str, float]) -> None:
    print(f"{section} threshold report:", file=sys.stderr)
    for key, minimum in thresholds.items():
        value = summary[key]
        status = "PASS" if value >= minimum else "FAIL"
        print(f"- {status} {key}: {value:.4f} / required {minimum:.4f}", file=sys.stderr)


def _source_chunks(case: dict[str, Any]) -> list[dict[str, str]]:
    if "source_chunks" in case:
        return [
            {
                "document_id": str(chunk["document_id"]),
                "chunk_id": str(chunk["chunk_id"]),
                "document_title": str(chunk.get("document_title") or chunk["document_id"]),
                "collection_id": str(chunk.get("collection_id") or case.get("collection_id") or ""),
                "content": str(chunk["content"]),
            }
            for chunk in case["source_chunks"]
        ]
    return [
        {
            "document_id": str(case.get("expected_source_documents", [_ZERO_UUID])[0]),
            "chunk_id": str(case.get("expected_source_chunks", [_ZERO_UUID])[0]),
            "document_title": "Synthetic Eval",
            "collection_id": str(case.get("collection_id") or ""),
            "content": str(case["context"]),
        }
    ]


def _apply_negative_case_scores(
    case: dict[str, Any],
    result: dict[str, object],
    answer: str,
    retrieved_chunks: list[dict[str, str]],
    *,
    require_abstention: bool = False,
) -> dict[str, object]:
    if not case.get("expected_no_answer"):
        return result
    answer_lower = answer.lower()
    abstained = _is_abstention(answer_lower)
    no_sources = not retrieved_chunks
    passed = 1.0 if abstained or (no_sources and not require_abstention) else 0.0
    result["answer"] = {"faithfulness": passed, "answer_relevancy": passed, "context_recall": 1.0 if no_sources else 0.0}
    result["retrieval"] = _score_retrieval(case, retrieved_chunks)
    return result


def _is_abstention(answer_lower: str) -> bool:
    return any(
        phrase in answer_lower
        for phrase in (
            "could not find",
            "cannot find",
            "can't find",
            "do not know",
            "don't know",
            "insufficient",
            "not enough information",
            "not in the context",
            "provided context does not",
            "context provided does not",
            "context does not",
            "does not contain",
            "does not specify",
            "does not include",
            "not specify",
            "not specified",
            "not mentioned",
            "не знайш",
            "не можу знайти",
            "недостат",
            "немає",
        )
    )


def _expected_terms(case: dict[str, Any]) -> list[str]:
    return [str(term).lower() for term in case.get("expected_answer_terms", [])]


def _term_ratio(expected_terms: list[str], text: str) -> float:
    if not expected_terms:
        return 0.0
    lowered = text.lower()
    return round(sum(1 for term in expected_terms if term in lowered) / len(expected_terms), 4)


def _terms(text: str) -> list[str]:
    return [term.casefold() for term in _WORD_RE.findall(text) if len(term) > 2]


def _uuid_or_zero(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        return _ZERO_UUID


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Run Conserium query eval regression.")
    parser.add_argument("--dataset", default="evals/query_eval_set.json")
    parser.add_argument("--dataset-dir", default="")
    parser.add_argument("--min-faithfulness", type=float, default=None)
    parser.add_argument("--min-answer-relevancy", type=float, default=None)
    parser.add_argument("--min-context-recall", type=float, default=None)
    parser.add_argument("--min-answer-faithfulness", type=float, default=0.8)
    parser.add_argument("--min-answer-context-recall", type=float, default=0.75)
    parser.add_argument("--min-answer-relevance", type=float, default=0.75)
    parser.add_argument("--min-retrieval-hit-rate", type=float, default=0.9)
    parser.add_argument("--min-retrieval-source-recall", type=float, default=0.75)
    parser.add_argument("--min-retrieval-mrr", type=float, default=0.75)
    parser.add_argument("--min-noise-rejection", type=float, default=1.0)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--output", default="", help="Optional path to write the JSON eval report.")
    args = parser.parse_args()

    cases = _load_cases_from_dir(Path(args.dataset_dir)) if args.dataset_dir else _load_cases(Path(args.dataset))
    if args.base_url and args.token:
        results = [_score_api_case(args.base_url, args.token, case) for case in cases]
    else:
        import asyncio

        results = await asyncio.gather(*[_score_offline_case(case) for case in cases])

    answer_summary = _summarize(results, "answer", ["faithfulness", "answer_relevancy", "context_recall"])
    retrieval_summary = _summarize(results, "retrieval", ["hit_rate", "source_recall", "mrr", "noise_rejection"])
    output = {
        "answer_summary": answer_summary,
        "retrieval_summary": retrieval_summary,
        "collections": {
            "answer": _summarize_by_collection(results, "answer", ["faithfulness", "answer_relevancy", "context_recall"]),
            "retrieval": _summarize_by_collection(results, "retrieval", ["hit_rate", "source_recall", "mrr", "noise_rejection"]),
        },
        "results": results,
    }
    rendered_output = json.dumps(output, indent=2, sort_keys=True)
    print(rendered_output)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered_output + "\n", encoding="utf-8")

    answer_thresholds = {
        "faithfulness": args.min_faithfulness if args.min_faithfulness is not None else args.min_answer_faithfulness,
        "answer_relevancy": args.min_answer_relevancy
        if args.min_answer_relevancy is not None
        else args.min_answer_relevance,
        "context_recall": args.min_context_recall
        if args.min_context_recall is not None
        else args.min_answer_context_recall,
    }
    retrieval_thresholds = {
        "hit_rate": args.min_retrieval_hit_rate,
        "source_recall": args.min_retrieval_source_recall,
        "mrr": args.min_retrieval_mrr,
        "noise_rejection": args.min_noise_rejection,
    }
    _print_threshold_report("Answer", answer_summary, answer_thresholds)
    _print_threshold_report("Retrieval", retrieval_summary, retrieval_thresholds)
    print("Per-collection retrieval threshold report:", file=sys.stderr)
    collection_summaries = cast("dict[str, dict[str, dict[str, float]]]", output["collections"])
    collection_retrieval = collection_summaries["retrieval"]
    for collection_id, summary in collection_retrieval.items():
        print(f"- {collection_id}", file=sys.stderr)
        for key, minimum in retrieval_thresholds.items():
            value = summary[key]
            status = "PASS" if value >= minimum else "FAIL"
            print(f"  - {status} {key}: {value:.4f} / required {minimum:.4f}", file=sys.stderr)
    failures = [
        *[f"answer.{failure}" for failure in _threshold_failures(answer_summary, answer_thresholds)],
        *[f"retrieval.{failure}" for failure in _threshold_failures(retrieval_summary, retrieval_thresholds)],
        *[
            f"collection_retrieval.{failure}"
            for failure in _collection_threshold_failures(collection_retrieval, retrieval_thresholds)
        ],
    ]
    if failures:
        print("Eval regression failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(_main()))
