from unittest.mock import patch


def test_embed_and_finalize_document_delegates_to_use_case_runner() -> None:
    from src.infrastructure.celery.tasks.embeddings import embed_and_finalize_document

    with patch(
        "src.infrastructure.celery.tasks.embeddings._run_process_document_embeddings_use_case",
        return_value={"document_id": "doc-id", "status": "READY"},
    ) as run_use_case:
        result = embed_and_finalize_document.run("doc-id", "hello", [{"content": "hello", "chunk_index": 0}])

    assert result == {"document_id": "doc-id", "status": "READY"}
    run_use_case.assert_called_once_with(
        document_id="doc-id",
        raw_text="hello",
        chunks_data=[{"content": "hello", "chunk_index": 0}],
        expected_content_hash=None,
    )
