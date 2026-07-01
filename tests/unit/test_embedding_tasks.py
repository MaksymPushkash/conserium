from unittest.mock import AsyncMock, patch

import pytest


class _FakeEnrichmentTask:
    def __init__(self) -> None:
        self.dispatched: list[tuple[str, int | None]] = []
        self._priority: int | None = None

    def kicker(self) -> "_FakeEnrichmentTask":
        return self

    def with_labels(self, *, priority: int) -> "_FakeEnrichmentTask":
        self._priority = priority
        return self

    async def kiq(self, document_id: str) -> None:
        self.dispatched.append((document_id, self._priority))


@pytest.mark.asyncio
async def test_embed_and_finalize_document_delegates_to_service_runner() -> None:
    from src.documents.task_embedding import run_embed_and_finalize_document_task

    enrichment_task = _FakeEnrichmentTask()
    with patch(
        "src.documents.task_embedding.process_document_embeddings",
        new_callable=AsyncMock,
        return_value={"document_id": "doc-id", "status": "READY"},
    ) as run_service:
        result = await run_embed_and_finalize_document_task(
            task_id="task-id",
            retry_count=0,
            document_id="doc-id",
            raw_text="hello",
            chunks_data=[{"content": "hello", "chunk_index": 0}],
            expected_content_hash=None,
            enrichment_task=enrichment_task,
        )

    assert result == {"document_id": "doc-id", "status": "READY"}
    run_service.assert_awaited_once_with(
        document_id="doc-id",
        raw_text="hello",
        chunks_data=[{"content": "hello", "chunk_index": 0}],
        expected_content_hash=None,
    )
    assert enrichment_task.dispatched == [("doc-id", 5)]
