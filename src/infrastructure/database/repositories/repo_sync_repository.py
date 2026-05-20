import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, nullsfirst, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dtos.repo_sync_dtos import RepoSyncDTO, RepoSyncItemDTO
from src.application.ports.persistence.repo_sync_repository import IRepoSyncRepository
from src.infrastructure.database.models.repo_sync import RepoSyncItemModel, RepoSyncModel


class SQLAlchemyRepoSyncRepository(IRepoSyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user_id(self, user_id: UUID) -> list[RepoSyncDTO]:
        result = await self._session.execute(
            select(RepoSyncModel)
            .where(RepoSyncModel.user_id == user_id)
            .order_by(RepoSyncModel.created_at.desc())
        )
        return [self._to_sync_dto(model) for model in result.scalars().all()]

    async def list_due_for_sync(self, *, before: datetime, limit: int) -> list[RepoSyncDTO]:
        result = await self._session.execute(
            select(RepoSyncModel)
            .where(RepoSyncModel.status != "running")
            .where(or_(RepoSyncModel.last_synced_at.is_(None), RepoSyncModel.last_synced_at <= before))
            .order_by(nullsfirst(RepoSyncModel.last_synced_at.asc()), RepoSyncModel.created_at.asc())
            .limit(limit)
        )
        return [self._to_sync_dto(model) for model in result.scalars().all()]

    async def get_by_id(self, repo_sync_id: UUID) -> RepoSyncDTO | None:
        result = await self._session.execute(select(RepoSyncModel).where(RepoSyncModel.id == repo_sync_id))
        model = result.scalar_one_or_none()
        return self._to_sync_dto(model) if model else None

    async def get_by_repo(
        self,
        *,
        user_id: UUID,
        owner: str,
        repo: str,
        branch: str,
    ) -> RepoSyncDTO | None:
        result = await self._session.execute(
            select(RepoSyncModel).where(
                RepoSyncModel.user_id == user_id,
                RepoSyncModel.owner == owner,
                RepoSyncModel.repo == repo,
                RepoSyncModel.branch == branch,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_sync_dto(model) if model else None

    async def create(
        self,
        *,
        id: UUID,
        user_id: UUID,
        collection_id: UUID,
        provider: str,
        owner: str,
        repo: str,
        branch: str,
    ) -> RepoSyncDTO:
        model = RepoSyncModel(
            id=id,
            user_id=user_id,
            collection_id=collection_id,
            provider=provider,
            owner=owner,
            repo=repo,
            branch=branch,
            status="idle",
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_sync_dto(model)

    async def update_state(
        self,
        *,
        repo_sync_id: UUID,
        status: str,
        last_error: str | None = None,
        last_synced_at: datetime | None = None,
    ) -> RepoSyncDTO:
        result = await self._session.execute(select(RepoSyncModel).where(RepoSyncModel.id == repo_sync_id))
        model = result.scalar_one()
        model.status = status
        model.last_error = last_error
        if last_synced_at is not None:
            model.last_synced_at = last_synced_at
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_sync_dto(model)

    async def list_items(self, repo_sync_id: UUID) -> list[RepoSyncItemDTO]:
        result = await self._session.execute(
            select(RepoSyncItemModel)
            .where(RepoSyncItemModel.repo_sync_id == repo_sync_id)
            .order_by(RepoSyncItemModel.path.asc())
        )
        return [self._to_item_dto(model) for model in result.scalars().all()]

    async def get_item_by_path(self, *, repo_sync_id: UUID, path: str) -> RepoSyncItemDTO | None:
        result = await self._session.execute(
            select(RepoSyncItemModel).where(
                RepoSyncItemModel.repo_sync_id == repo_sync_id,
                RepoSyncItemModel.path == path,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_item_dto(model) if model else None

    async def upsert_item(
        self,
        *,
        repo_sync_id: UUID,
        path: str,
        sha: str,
        document_id: UUID,
        source_url: str,
        synced_at: datetime,
    ) -> RepoSyncItemDTO:
        result = await self._session.execute(
            select(RepoSyncItemModel).where(
                RepoSyncItemModel.repo_sync_id == repo_sync_id,
                RepoSyncItemModel.path == path,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            model = RepoSyncItemModel(
                id=uuid.uuid4(),
                repo_sync_id=repo_sync_id,
                path=path,
                sha=sha,
                document_id=document_id,
                source_url=source_url,
                last_synced_at=synced_at,
            )
            self._session.add(model)
        else:
            model.sha = sha
            model.document_id = document_id
            model.source_url = source_url
            model.last_synced_at = synced_at
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_item_dto(model)

    async def delete_item(self, item_id: UUID) -> None:
        await self._session.execute(delete(RepoSyncItemModel).where(RepoSyncItemModel.id == item_id))

    @staticmethod
    def _to_sync_dto(model: RepoSyncModel) -> RepoSyncDTO:
        return RepoSyncDTO(
            id=model.id,
            user_id=model.user_id,
            collection_id=model.collection_id,
            provider=model.provider,
            owner=model.owner,
            repo=model.repo,
            branch=model.branch,
            status=model.status,
            last_error=model.last_error,
            last_synced_at=model.last_synced_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_item_dto(model: RepoSyncItemModel) -> RepoSyncItemDTO:
        return RepoSyncItemDTO(
            id=model.id,
            repo_sync_id=model.repo_sync_id,
            path=model.path,
            sha=model.sha,
            document_id=model.document_id,
            source_url=model.source_url,
            last_synced_at=model.last_synced_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
