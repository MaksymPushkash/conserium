from unittest.mock import AsyncMock, patch


def test_process_document_delegates_to_pipeline() -> None:
    from src.infrastructure.celery.tasks.document_ingestion_task import process_document

    with patch(
        "src.infrastructure.celery.tasks.document_ingestion_task.process_document_ingestion",
        new_callable=AsyncMock,
        return_value={"document_id": "doc-id", "status": "EMBEDDING_QUEUED"},
    ) as run_use_case:
        result = process_document.run("doc-id")

    assert result == {"document_id": "doc-id", "status": "EMBEDDING_QUEUED"}
    run_use_case.assert_called_once_with("doc-id")
