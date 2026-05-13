from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

JsonObject = dict[str, Any]

_ABSTENTION_PHRASES = (
    "could not find",
    "cannot find",
    "can't find",
    "do not know",
    "don't know",
    "insufficient",
    "not enough information",
    "not in the context",
    "context does not",
    "не знайш",
    "не можу знайти",
    "недостат",
    "немає",
)


@dataclass(frozen=True, slots=True)
class SeededDocument:
    key: str
    id: str
    collection_id: str
    noise: bool


@dataclass(frozen=True, slots=True)
class SeededCollection:
    key: str
    id: str


@dataclass(frozen=True, slots=True)
class LiveEvalContext:
    collections: dict[str, SeededCollection]
    documents: dict[str, SeededDocument]


class ApiClient:
    def __init__(self, base_url: str, token: str | None = None) -> None:
        self._base_url = _normalize_base_url(base_url)
        self._token = token

    def with_token(self, token: str) -> ApiClient:
        return ApiClient(self._base_url, token)

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: JsonObject | None = None,
        timeout: int = 60,
    ) -> JsonObject:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(
            f"{self._base_url}/api/v1{path}",
            data=data,
            headers=headers,
            method=method,
        )
        print(f"[live-eval] {method} {path}", file=sys.stderr, flush=True)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return cast("JsonObject", json.loads(body)) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if _looks_like_html(detail):
                raise RuntimeError(
                    f"{method} {path} failed with HTTP {exc.code} from {self._base_url}: "
                    "received HTML instead of JSON. "
                    "PRODUCTION_API_BASE_URL must point to the backend API origin, "
                    "for example https://api.cortexx.me, not the frontend app URL. "
                    "If it already points to the API origin, the public nginx/backend route is unhealthy."
                ) from exc
            raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"{method} {path} failed against {self._base_url}: {exc.reason}. "
                "Check PRODUCTION_API_BASE_URL DNS, TLS, and nginx routing."
            ) from exc


def _normalize_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/api/v1"):
        return normalized[: -len("/api/v1")]
    return normalized


def _looks_like_html(body: str) -> bool:
    stripped = body.lstrip().lower()
    return stripped.startswith("<!doctype html") or stripped.startswith("<html")


def _authenticate(base_url: str, email: str, password: str, create_user: bool) -> ApiClient:
    client = ApiClient(base_url)
    if create_user:
        try:
            print("[live-eval] registering live eval user", file=sys.stderr, flush=True)
            token_payload = client.request(
                "POST",
                "/auth/register",
                payload={"email": email, "password": password, "display_name": "Cortex Live Eval"},
            )
            return client.with_token(str(token_payload["access_token"]))
        except RuntimeError as exc:
            print(f"Registration skipped: {exc}", file=sys.stderr)

    print("[live-eval] logging in live eval user", file=sys.stderr, flush=True)
    token_payload = client.request("POST", "/auth/login", payload={"email": email, "password": password})
    return client.with_token(str(token_payload["access_token"]))


def _seed_dataset(
    client: ApiClient,
    dataset: JsonObject,
    run_id: str,
    wait_timeout_seconds: int,
    context: LiveEvalContext,
) -> None:
    for collection_spec in dataset["collections"]:
        collection_key = str(collection_spec["key"])
        print(f"[live-eval] seeding collection {collection_key}", file=sys.stderr, flush=True)
        collection = client.request(
            "POST",
            "/collections",
            payload={
                "name": f"Live Eval {run_id} - {collection_spec['name']}",
                "description": "Temporary collection created by production retrieval validation.",
                "color": "#2563EB",
            },
        )
        collection_id = str(collection["id"])
        context.collections[collection_key] = SeededCollection(key=collection_key, id=collection_id)
        for document_spec in collection_spec.get("documents", []):
            seeded = _ingest_text_document(
                client=client,
                collection_id=collection_id,
                document_spec=cast("JsonObject", document_spec),
                noise=False,
                wait_timeout_seconds=wait_timeout_seconds,
            )
            context.documents[seeded.key] = seeded
        for document_spec in collection_spec.get("noise_documents", []):
            seeded = _ingest_text_document(
                client=client,
                collection_id=collection_id,
                document_spec=cast("JsonObject", document_spec),
                noise=True,
                wait_timeout_seconds=wait_timeout_seconds,
            )
            context.documents[seeded.key] = seeded


def _ingest_text_document(
    *,
    client: ApiClient,
    collection_id: str,
    document_spec: JsonObject,
    noise: bool,
    wait_timeout_seconds: int,
) -> SeededDocument:
    print(
        f"[live-eval] ingesting {'noise ' if noise else ''}document {document_spec['key']}",
        file=sys.stderr,
        flush=True,
    )
    document = client.request(
        "POST",
        "/ingest",
        payload={
            "title": str(document_spec["title"]),
            "type": "TEXT",
            "collection_id": collection_id,
            "raw_content": str(document_spec["content"]),
            "language": "en",
        },
    )
    document_id = str(document["id"])
    try:
        _wait_document_ready(client, document_id, wait_timeout_seconds)
    except Exception:
        print(
            f"[live-eval] deleting timed-out/failed seed document {document_id}",
            file=sys.stderr,
            flush=True,
        )
        try:
            client.request("DELETE", f"/documents/{document_id}", timeout=30)
        except RuntimeError as cleanup_error:
            print(f"[live-eval] failed to delete seed document {document_id}: {cleanup_error}", file=sys.stderr)
        raise
    return SeededDocument(key=str(document_spec["key"]), id=document_id, collection_id=collection_id, noise=noise)


def _wait_document_ready(client: ApiClient, document_id: str, wait_timeout_seconds: int) -> None:
    deadline = time.monotonic() + wait_timeout_seconds
    last_status = ""
    while time.monotonic() < deadline:
        status_payload = client.request("GET", f"/documents/{document_id}/status", timeout=30)
        status = str(status_payload.get("status", "")).upper()
        if status != last_status:
            print(
                f"[live-eval] document {document_id} status={status} progress={status_payload.get('progress')}",
                file=sys.stderr,
                flush=True,
            )
            last_status = status
        if status == "READY":
            return
        if status == "FAILED":
            reason = status_payload.get("failure_reason") or status_payload.get("message")
            raise RuntimeError(f"document {document_id} failed processing: {reason}")
        time.sleep(2)
    raise TimeoutError(f"document {document_id} was not READY after {wait_timeout_seconds} seconds")


def _run_cases(client: ApiClient, dataset: JsonObject, context: LiveEvalContext) -> list[JsonObject]:
    results: list[JsonObject] = []
    noise_document_ids = {document.id for document in context.documents.values() if document.noise}
    for collection_spec in dataset["collections"]:
        collection_key = str(collection_spec["key"])
        collection_id = context.collections[collection_key].id
        for case in collection_spec["cases"]:
            results.append(
                _run_case(
                    client=client,
                    case=cast("JsonObject", case),
                    collection_id=collection_id,
                    context=context,
                    noise_document_ids=noise_document_ids,
                )
            )
    return results


def _run_case(
    *,
    client: ApiClient,
    case: JsonObject,
    collection_id: str,
    context: LiveEvalContext,
    noise_document_ids: set[str],
) -> JsonObject:
    conversation_id = str(uuid.uuid4()) if case.get("conversation_seed_queries") else None
    for seed_query in case.get("conversation_seed_queries", []):
        _query_api(
            client=client,
            query=str(seed_query),
            collection_id=collection_id,
            conversation_id=conversation_id,
            limit=int(case.get("limit", 5)),
        )

    payload = _query_api(
        client=client,
        query=str(case["query"]),
        collection_id=collection_id,
        conversation_id=conversation_id,
        limit=int(case.get("limit", 5)),
    )
    sources = cast("list[JsonObject]", payload.get("sources", []))
    answer = str(payload.get("answer", ""))
    source_document_ids = [str(source.get("document_id", "")) for source in sources]
    expected_document_ids = [context.documents[str(key)].id for key in case.get("expected_document_keys", [])]
    retrieval = _score_retrieval(source_document_ids, expected_document_ids)
    collection_scope = _score_collection_scope(source_document_ids, collection_id, context)
    noise_rejection = 1.0 if not (set(source_document_ids) & noise_document_ids) else 0.0
    abstention = _score_abstention(answer) if case.get("expected_no_answer") or case.get("must_abstain") else None
    result: JsonObject = {
        "id": case["id"],
        "kind": case.get("kind", "retrieval"),
        "collection_id": collection_id,
        "query": case["query"],
        "answer": answer,
        "retrieval": retrieval,
        "collection_scope": collection_scope,
        "noise_rejection": noise_rejection,
        "sources": [
            {
                "document_id": source.get("document_id"),
                "chunk_id": source.get("chunk_id"),
                "document_title": source.get("document_title"),
                "score": source.get("score"),
                "used_in_answer": source.get("used_in_answer"),
            }
            for source in sources
        ],
    }
    if abstention is not None:
        result["abstention"] = abstention
    return result


def _query_api(
    *,
    client: ApiClient,
    query: str,
    collection_id: str,
    conversation_id: str | None,
    limit: int,
) -> JsonObject:
    print(f"[live-eval] query collection={collection_id} text={query!r}", file=sys.stderr, flush=True)
    payload: JsonObject = {"query": query, "collection_id": collection_id, "limit": limit}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    return client.request("POST", "/query", payload=payload, timeout=90)


def _score_retrieval(source_document_ids: list[str], expected_document_ids: list[str]) -> JsonObject:
    if not expected_document_ids:
        return {"hit_rate": 1.0, "source_recall": 1.0, "mrr": 1.0}
    matches = [document_id in set(expected_document_ids) for document_id in source_document_ids]
    matched_expected = set(source_document_ids) & set(expected_document_ids)
    mrr = 0.0
    for rank, matched in enumerate(matches, start=1):
        if matched:
            mrr = round(1 / rank, 4)
            break
    return {
        "hit_rate": 1.0 if any(matches) else 0.0,
        "source_recall": round(len(matched_expected) / len(expected_document_ids), 4),
        "mrr": mrr,
    }


def _score_collection_scope(source_document_ids: list[str], collection_id: str, context: LiveEvalContext) -> float:
    if not source_document_ids:
        return 1.0
    document_collections = {document.id: document.collection_id for document in context.documents.values()}
    return 1.0 if all(document_collections.get(document_id) == collection_id for document_id in source_document_ids) else 0.0


def _score_abstention(answer: str) -> float:
    normalized = answer.casefold()
    return 1.0 if any(phrase in normalized for phrase in _ABSTENTION_PHRASES) else 0.0


def _summarize(results: list[JsonObject]) -> JsonObject:
    retrieval_cases = [result for result in results if "abstention" not in result]
    abstention_cases = [result for result in results if "abstention" in result]
    rewrite_cases = [result for result in results if result.get("kind") == "query_rewrite"]
    return {
        "retrieval": {
            "hit_rate": _average([float(result["retrieval"]["hit_rate"]) for result in retrieval_cases]),
            "source_recall": _average([float(result["retrieval"]["source_recall"]) for result in retrieval_cases]),
            "mrr": _average([float(result["retrieval"]["mrr"]) for result in retrieval_cases]),
            "noise_rejection": _average([float(result["noise_rejection"]) for result in results]),
            "collection_scope": _average([float(result["collection_scope"]) for result in results]),
        },
        "abstention": {
            "answer_must_abstain": _average([float(result["abstention"]) for result in abstention_cases]),
        },
        "query_rewrite": {
            "source_recall": _average([float(result["retrieval"]["source_recall"]) for result in rewrite_cases]),
        },
    }


def _average(values: list[float]) -> float:
    if not values:
        return 1.0
    return round(sum(values) / len(values), 4)


def _threshold_failures(summary: JsonObject, args: argparse.Namespace) -> list[str]:
    checks = {
        "retrieval.hit_rate": (float(summary["retrieval"]["hit_rate"]), args.min_retrieval_hit_rate),
        "retrieval.source_recall": (float(summary["retrieval"]["source_recall"]), args.min_retrieval_source_recall),
        "retrieval.mrr": (float(summary["retrieval"]["mrr"]), args.min_retrieval_mrr),
        "retrieval.noise_rejection": (float(summary["retrieval"]["noise_rejection"]), args.min_noise_rejection),
        "retrieval.collection_scope": (float(summary["retrieval"]["collection_scope"]), args.min_collection_scope),
        "abstention.answer_must_abstain": (
            float(summary["abstention"]["answer_must_abstain"]),
            args.min_abstention_rate,
        ),
        "query_rewrite.source_recall": (
            float(summary["query_rewrite"]["source_recall"]),
            args.min_query_rewrite_source_recall,
        ),
    }
    return [f"{name}: {value:.4f} < required {minimum:.4f}" for name, (value, minimum) in checks.items() if value < minimum]


def _cleanup(client: ApiClient, context: LiveEvalContext) -> None:
    document_ids = [document.id for document in context.documents.values()]
    if document_ids:
        try:
            print(f"[live-eval] cleaning up {len(document_ids)} seeded documents", file=sys.stderr, flush=True)
            client.request("POST", "/documents/bulk/delete", payload={"document_ids": document_ids})
        except RuntimeError as exc:
            print(f"Live eval cleanup failed for documents: {exc}", file=sys.stderr)
    for collection in context.collections.values():
        try:
            print(f"[live-eval] cleaning up collection {collection.key}", file=sys.stderr, flush=True)
            client.request("DELETE", f"/collections/{collection.id}")
        except RuntimeError as exc:
            print(f"Live eval cleanup failed for collection {collection.id}: {exc}", file=sys.stderr)


def _load_dataset(path: Path) -> JsonObject:
    return cast("JsonObject", json.loads(path.read_text(encoding="utf-8")))


def _write_report(path: str, report: JsonObject) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _main() -> int:
    parser = argparse.ArgumentParser(description="Seed and validate live Cortex retrieval through the public API.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--dataset", default="evals/live/seed.json")
    parser.add_argument("--output", default="artifacts/live-retrieval-eval-report.json")
    parser.add_argument("--create-user", action="store_true")
    parser.add_argument("--keep-seed", action="store_true")
    parser.add_argument("--wait-timeout-seconds", type=int, default=240)
    parser.add_argument("--min-retrieval-hit-rate", type=float, default=0.9)
    parser.add_argument("--min-retrieval-source-recall", type=float, default=0.9)
    parser.add_argument("--min-retrieval-mrr", type=float, default=0.75)
    parser.add_argument("--min-noise-rejection", type=float, default=1.0)
    parser.add_argument("--min-collection-scope", type=float, default=1.0)
    parser.add_argument("--min-abstention-rate", type=float, default=1.0)
    parser.add_argument("--min-query-rewrite-source-recall", type=float, default=0.8)
    args = parser.parse_args()

    dataset = _load_dataset(Path(args.dataset))
    client = _authenticate(args.base_url, args.email, args.password, args.create_user)
    context = LiveEvalContext(collections={}, documents={})
    try:
        run_id = uuid.uuid4().hex[:8]
        _seed_dataset(client, dataset, run_id, args.wait_timeout_seconds, context)
        results = _run_cases(client, dataset, context)
        summary = _summarize(results)
        report = {
            "base_url": args.base_url,
            "summary": summary,
            "results": results,
            "seed": {
                "collections": {key: collection.id for key, collection in context.collections.items()},
                "documents": {key: document.id for key, document in context.documents.items()},
            },
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        _write_report(args.output, report)
        failures = _threshold_failures(summary, args)
        if failures:
            print("Live retrieval validation failed:", file=sys.stderr)
            for failure in failures:
                print(f"- {failure}", file=sys.stderr)
            return 1
        return 0
    finally:
        if not args.keep_seed and context.collections:
            _cleanup(client, context)


if __name__ == "__main__":
    sys.exit(_main())
