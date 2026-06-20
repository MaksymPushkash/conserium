from unittest.mock import AsyncMock, patch


def test_process_image_document_delegates_to_service_runner() -> None:
    from src.documents.tasks import process_image_document

    with patch(
        "src.documents.task_media.process_image_document_worker",
        new_callable=AsyncMock,
        return_value={"document_id": "doc-id", "status": "EMBEDDING_QUEUED"},
    ) as run_service:
        result = process_image_document.run("doc-id")

    assert result == {"document_id": "doc-id", "status": "EMBEDDING_QUEUED"}
    run_service.assert_called_once_with("doc-id")
