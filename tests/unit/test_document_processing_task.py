from unittest.mock import patch

import pytest

from src.infrastructure.celery.tasks.document_processing import _ExtractedDocument, _PageRange, _step_chunk, _step_embed


class _Log:
    def info(self, *args: object, **kwargs: object) -> None:
        return None


def test_step_chunk_assigns_pdf_page_number_from_char_ranges() -> None:
    extracted = _ExtractedDocument(
        text="First page text.\n\nSecond page text.",
        page_ranges=[
            _PageRange(page_number=1, start_char=0, end_char=16),
            _PageRange(page_number=2, start_char=18, end_char=35),
        ],
    )

    chunks = _step_chunk(extracted, _Log())

    assert chunks[0]["page_number"] == 1


def test_step_embed_fails_without_openai_key() -> None:
    with patch("src.infrastructure.celery.tasks.document_processing.settings.OPENAI_API_KEY", ""):
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            _step_embed([{"content": "hello"}], _Log())


def test_process_document_delegates_to_pipeline() -> None:
    from src.infrastructure.celery.tasks.document_processing import process_document

    class _Request:
        id = "task-id"
        retries = 0

    class _Task:
        request = _Request()
        max_retries = 3

    with patch(
        "src.infrastructure.ingestion.document_processing_pipeline.DocumentProcessingPipeline.process",
        return_value={"document_id": "doc-id", "status": "EMBEDDING_QUEUED"},
    ) as process:
        result = process_document(_Task(), "doc-id")

    assert result == {"document_id": "doc-id", "status": "EMBEDDING_QUEUED"}
    process.assert_called_once()
