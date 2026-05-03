from unittest.mock import patch


def test_process_document_delegates_to_pipeline() -> None:
    from src.infrastructure.celery.tasks.document_processing import process_document

    with patch(
        "src.infrastructure.celery.tasks.document_processing._run_process_document_use_case",
        return_value={"document_id": "doc-id", "status": "EMBEDDING_QUEUED"},
    ) as run_use_case:
        result = process_document.run("doc-id")

    assert result == {"document_id": "doc-id", "status": "EMBEDDING_QUEUED"}
    run_use_case.assert_called_once_with("doc-id")
