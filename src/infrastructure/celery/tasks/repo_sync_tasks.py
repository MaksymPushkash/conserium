from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from src.infrastructure.celery.composition import run_due_repo_syncs
from src.infrastructure.celery.dependencies import run_worker_async

logger = logging.getLogger(__name__)


@shared_task(  # type: ignore[untyped-decorator]
    name="src.infrastructure.celery.tasks.repo_sync_tasks.run_due_repo_syncs_task",
    queue="cleanup",
    bind=True,
    soft_time_limit=600,
    time_limit=720,
)
def run_due_repo_syncs_task(self: Any) -> dict[str, int]:
    try:
        return run_worker_async(run_due_repo_syncs())
    except Exception as exc:
        logger.exception("Scheduled repo sync failed: %s", exc)
        return {"queued": 0, "completed": 0, "failed": 1}
