from unittest.mock import patch


def test_process_audio_document_delegates_to_use_case_runner() -> None:
    from src.infrastructure.celery.tasks.hf_processing import process_audio_document

    with patch(
        "src.infrastructure.celery.tasks.hf_processing._run_process_audio_document_use_case",
        return_value={"document_id": "doc-id", "status": "EMBEDDING_QUEUED"},
    ) as run_use_case:
        result = process_audio_document.run("doc-id")

    assert result == {"document_id": "doc-id", "status": "EMBEDDING_QUEUED"}
    run_use_case.assert_called_once_with(document_id="doc-id")


def test_process_image_document_delegates_to_use_case_runner() -> None:
    from src.infrastructure.celery.tasks.hf_processing import process_image_document

    with patch(
        "src.infrastructure.celery.tasks.hf_processing._run_process_image_document_use_case",
        return_value={"document_id": "doc-id", "status": "EMBEDDING_QUEUED"},
    ) as run_use_case:
        result = process_image_document.run("doc-id")

    assert result == {"document_id": "doc-id", "status": "EMBEDDING_QUEUED"}
    run_use_case.assert_called_once_with(document_id="doc-id")
