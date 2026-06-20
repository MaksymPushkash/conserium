from __future__ import annotations

import logging

from src.repo_syncs.worker import drain_repo_sync_outbox, run_due_repo_syncs
from src.worker.dependencies import run_worker_async

logger = logging.getLogger(__name__)


def run_due_repo_syncs_task_impl() -> dict[str, int]:
    try:
        return run_worker_async(run_due_repo_syncs())
    except Exception as exc:
        logger.exception("Scheduled repo sync failed: %s", exc)
        return {"queued": 0, "completed": 0, "failed": 1}


def run_drain_repo_sync_outbox_task(limit: int = 100) -> dict[str, int]:
    try:
        return run_worker_async(drain_repo_sync_outbox(limit=limit))
    except Exception as exc:
        logger.exception("Repo sync outbox drain failed: %s", exc)
        return {"claimed": 0, "dispatched": 0, "failed": 1, "permanently_failed": 0}
