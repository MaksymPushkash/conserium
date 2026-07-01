from src.repo_syncs.service import RepoSyncService
from src.worker.dispatcher import TaskiqTaskDispatcher


def get_repo_sync_service() -> RepoSyncService:
    return RepoSyncService()


def get_task_dispatcher() -> TaskiqTaskDispatcher:
    return TaskiqTaskDispatcher()
