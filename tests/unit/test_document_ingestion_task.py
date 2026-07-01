from unittest.mock import ANY, AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_process_document_delegates_to_pipeline() -> None:
    from src.documents.task_ingestion import run_process_document_task

    with patch(
        "src.documents.task_ingestion.acknowledge_and_process_document_ingestion",
        new_callable=AsyncMock,
        return_value={"document_id": "doc-id", "status": "EMBEDDING_QUEUED"},
    ) as run_service:
        result = await run_process_document_task(task_id="task-id", retry_count=0, document_id="doc-id")

    assert result == {"document_id": "doc-id", "status": "EMBEDDING_QUEUED"}
    run_service.assert_called_once_with(task_id=ANY, document_id="doc-id")
