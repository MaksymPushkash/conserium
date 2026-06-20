from unittest.mock import AsyncMock, patch


def test_embed_and_finalize_document_delegates_to_service_runner() -> None:
    from src.documents.tasks import embed_and_finalize_document

    with (
        patch(
            "src.documents.task_embedding.process_document_embeddings",
            new_callable=AsyncMock,
            return_value={"document_id": "doc-id", "status": "READY"},
        ) as run_service,
        patch("src.documents.tasks.enrich_document_task.apply_async") as dispatch_enrichment,
    ):
        result = embed_and_finalize_document.run("doc-id", "hello", [{"content": "hello", "chunk_index": 0}])

    assert result == {"document_id": "doc-id", "status": "READY"}
    run_service.assert_called_once_with(
        document_id="doc-id",
        raw_text="hello",
        chunks_data=[{"content": "hello", "chunk_index": 0}],
        expected_content_hash=None,
    )
    dispatch_enrichment.assert_called_once_with(args=["doc-id"], priority=5)
