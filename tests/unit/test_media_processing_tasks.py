from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_process_image_document_delegates_to_service_runner() -> None:
    from src.documents.task_media import run_process_image_document_task

    with patch(
        "src.documents.task_media.process_image_document_worker",
        new_callable=AsyncMock,
        return_value={"document_id": "doc-id", "status": "EMBEDDING_QUEUED"},
    ) as run_service:
        result = await run_process_image_document_task(task_id="task-id", retry_count=0, document_id="doc-id")

    assert result == {"document_id": "doc-id", "status": "EMBEDDING_QUEUED"}
    run_service.assert_awaited_once_with("doc-id")
