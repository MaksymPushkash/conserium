from __future__ import annotations

from src.repo_syncs.task_outbox import (
    run_drain_repo_sync_outbox_task,
    run_due_repo_syncs_task_impl,
    run_repo_sync_task_impl,
)
from src.worker.app import taskiq_broker
from src.worker.task_names import REPO_SYNC_OUTBOX_DRAIN_TASK, REPO_SYNC_RUN_DUE_TASK, REPO_SYNC_RUN_TASK


@taskiq_broker.task(
    task_name=REPO_SYNC_RUN_DUE_TASK,
    queue_name="cleanup",
    timeout=720,
    schedule=[
        {
            "schedule_id": "run-due-repo-syncs",
            "interval": 900.0,
            "labels": {"queue_name": "cleanup"},
        }
    ],
)
async def run_due_repo_syncs_task() -> dict[str, int]:
    return await run_due_repo_syncs_task_impl()


@taskiq_broker.task(
    task_name=REPO_SYNC_RUN_TASK,
    queue_name="cleanup",
    timeout=720,
)
async def run_repo_sync_task(user_id: str, repo_sync_id: str, max_files: int = 50) -> dict[str, object]:
    return await run_repo_sync_task_impl(user_id=user_id, repo_sync_id=repo_sync_id, max_files=max_files)


@taskiq_broker.task(
    task_name=REPO_SYNC_OUTBOX_DRAIN_TASK,
    queue_name="cleanup",
    timeout=360,
    schedule=[
        {
            "schedule_id": "drain-repo-sync-outbox",
            "interval": 60.0,
            "labels": {"queue_name": "cleanup"},
        }
    ],
)
async def drain_repo_sync_outbox_task(limit: int = 100) -> dict[str, int]:
    return await run_drain_repo_sync_outbox_task(limit=limit)


__all__ = ["drain_repo_sync_outbox_task", "run_due_repo_syncs_task", "run_repo_sync_task"]
