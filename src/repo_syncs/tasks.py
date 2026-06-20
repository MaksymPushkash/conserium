from __future__ import annotations

from typing import Any

from celery import shared_task

from src.repo_syncs.task_outbox import run_drain_repo_sync_outbox_task, run_due_repo_syncs_task_impl
from src.worker.task_names import REPO_SYNC_OUTBOX_DRAIN_TASK, REPO_SYNC_RUN_DUE_TASK


@shared_task(  # type: ignore[untyped-decorator]
    name=REPO_SYNC_RUN_DUE_TASK,
    queue="cleanup",
    bind=True,
    soft_time_limit=600,
    time_limit=720,
)
def run_due_repo_syncs_task(self: Any) -> dict[str, int]:
    return run_due_repo_syncs_task_impl()


@shared_task(  # type: ignore[untyped-decorator]
    name=REPO_SYNC_OUTBOX_DRAIN_TASK,
    queue="cleanup",
    bind=True,
    soft_time_limit=300,
    time_limit=360,
)
def drain_repo_sync_outbox_task(self: Any, limit: int = 100) -> dict[str, int]:
    return run_drain_repo_sync_outbox_task(limit=limit)


__all__ = ["drain_repo_sync_outbox_task", "run_due_repo_syncs_task"]
