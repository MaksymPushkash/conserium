from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.postgres import get_db_session, get_session_factory
from src.repo_syncs.service import RepoSyncExecutor, RepoSyncService, build_repo_sync_service


def get_repo_sync_service(session: AsyncSession = Depends(get_db_session)) -> RepoSyncService:
    return build_repo_sync_service(session)


def get_repo_sync_executor() -> RepoSyncExecutor:
    return RepoSyncExecutor(get_session_factory())
