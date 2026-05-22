from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from src.infrastructure.celery.composition import drain_repo_sync_outbox, run_due_repo_syncs
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


@shared_task(  # type: ignore[untyped-decorator]
    name="src.infrastructure.celery.tasks.repo_sync_tasks.drain_repo_sync_outbox_task",
    queue="cleanup",
    bind=True,
    soft_time_limit=300,
    time_limit=360,
)
def drain_repo_sync_outbox_task(self: Any, limit: int = 100) -> dict[str, int]:
    try:
        return run_worker_async(drain_repo_sync_outbox(limit=limit))
    except Exception as exc:
        logger.exception("Repo sync outbox drain failed: %s", exc)
        return {"claimed": 0, "dispatched": 0, "failed": 1, "permanently_failed": 0}
