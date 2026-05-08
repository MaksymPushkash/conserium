from unittest.mock import AsyncMock, patch


def test_process_audio_document_delegates_to_use_case_runner() -> None:
    from src.infrastructure.celery.tasks.media_processing_tasks import process_audio_document

    with patch(
        "src.infrastructure.celery.tasks.media_processing_tasks.process_audio_document_use_case",
        new_callable=AsyncMock,
        return_value={"document_id": "doc-id", "status": "EMBEDDING_QUEUED"},
    ) as run_use_case:
        result = process_audio_document.run("doc-id")

    assert result == {"document_id": "doc-id", "status": "EMBEDDING_QUEUED"}
    run_use_case.assert_called_once_with("doc-id")


def test_process_image_document_delegates_to_use_case_runner() -> None:
    from src.infrastructure.celery.tasks.media_processing_tasks import process_image_document

    with patch(
        "src.infrastructure.celery.tasks.media_processing_tasks.process_image_document_use_case",
        new_callable=AsyncMock,
        return_value={"document_id": "doc-id", "status": "EMBEDDING_QUEUED"},
    ) as run_use_case:
        result = process_image_document.run("doc-id")

    assert result == {"document_id": "doc-id", "status": "EMBEDDING_QUEUED"}
    run_use_case.assert_called_once_with("doc-id")
