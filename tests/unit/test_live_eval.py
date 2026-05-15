import json
from pathlib import Path

from scripts.run_live_eval import _score_abstention


def test_live_eval_abstention_accepts_context_provided_phrase() -> None:
    answer = "The context provided does not contain any information regarding the recommended database storage engine."

    assert _score_abstention(answer) == 1.0


def test_live_eval_abstention_accepts_does_not_contain_phrase() -> None:
    answer = "The provided context does not contain any information regarding a payroll tax rate."

    assert _score_abstention(answer) == 1.0


def test_live_eval_abstention_accepts_does_not_specify_phrase() -> None:
    answer = "The context provided does not specify a recommended database storage engine for the Auth collection."

    assert _score_abstention(answer) == 1.0


def test_live_eval_auth_noise_document_does_not_answer_storage_engine_case() -> None:
    dataset = json.loads(Path("evals/live/seed.json").read_text(encoding="utf-8"))
    auth_collection = next(collection for collection in dataset["collections"] if collection["key"] == "auth")
    noise_document = next(
        document for document in auth_collection["noise_documents"] if document["key"] == "auth_noise_storage"
    )
    searchable_text = f"{noise_document['title']} {noise_document['content']}".casefold()

    assert "database" not in searchable_text
    assert "storage engine" not in searchable_text
    assert "parquet" not in searchable_text
    assert "refresh" not in searchable_text
    assert "logout" not in searchable_text
    assert "token" not in searchable_text
