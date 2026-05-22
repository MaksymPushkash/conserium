import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, nullsfirst, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dtos.repo_sync_dtos import RepoSyncDTO, RepoSyncItemDTO, RepoSyncOutboxDTO
from src.application.ports.persistence.repo_sync_repository import IRepoSyncRepository
from src.infrastructure.database.models.repo_sync import RepoSyncItemModel, RepoSyncModel, RepoSyncOutboxModel


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
            .where(RepoSyncModel.status.notin_(("running", "queueing")))
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
        include_paths: list[str],
        exclude_paths: list[str],
    ) -> RepoSyncDTO:
        model = RepoSyncModel(
            id=id,
            user_id=user_id,
            collection_id=collection_id,
            provider=provider,
            owner=owner,
            repo=repo,
            branch=branch,
            include_paths=include_paths,
            exclude_paths=exclude_paths,
            status="idle",
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_sync_dto(model)

    async def update_filters(
        self,
        *,
        repo_sync_id: UUID,
        include_paths: list[str],
        exclude_paths: list[str],
    ) -> RepoSyncDTO:
        result = await self._session.execute(select(RepoSyncModel).where(RepoSyncModel.id == repo_sync_id))
        model = result.scalar_one()
        model.include_paths = include_paths
        model.exclude_paths = exclude_paths
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

    async def create_outbox(
        self,
        *,
        repo_sync_id: UUID,
        document_id: UUID,
        task_name: str,
    ) -> RepoSyncOutboxDTO:
        result = await self._session.execute(
            pg_insert(RepoSyncOutboxModel)
            .values(
                id=uuid.uuid4(),
                repo_sync_id=repo_sync_id,
                document_id=document_id,
                task_name=task_name,
                status="pending",
                attempts=0,
            )
            .on_conflict_do_update(
                index_elements=[
                    RepoSyncOutboxModel.repo_sync_id,
                    RepoSyncOutboxModel.document_id,
                    RepoSyncOutboxModel.task_name,
                ],
                index_where=RepoSyncOutboxModel.status != "dispatched",
                set_={
                    "status": "pending",
                    "locked_at": None,
                    "last_error": None,
                },
            )
            .returning(RepoSyncOutboxModel)
        )
        model = result.scalar_one()
        return self._to_outbox_dto(model)

    async def claim_outbox_batch(
        self,
        *,
        limit: int,
        locked_at: datetime,
        stale_before: datetime,
        max_attempts: int,
    ) -> list[RepoSyncOutboxDTO]:
        result = await self._session.execute(
            select(RepoSyncOutboxModel)
            .where(
                RepoSyncOutboxModel.status.in_(("pending", "processing")),
                RepoSyncOutboxModel.attempts < max_attempts,
                or_(
                    RepoSyncOutboxModel.status == "pending",
                    RepoSyncOutboxModel.locked_at <= stale_before,
                ),
            )
            .order_by(RepoSyncOutboxModel.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        models = result.scalars().all()
        for model in models:
            model.status = "processing"
            model.locked_at = locked_at
            model.attempts += 1
        await self._session.flush()
        return [self._to_outbox_dto(model) for model in models]

    async def mark_outbox_dispatched(self, outbox_id: UUID, dispatched_at: datetime) -> RepoSyncOutboxDTO:
        result = await self._session.execute(select(RepoSyncOutboxModel).where(RepoSyncOutboxModel.id == outbox_id))
        model = result.scalar_one()
        model.status = "dispatched"
        model.dispatched_at = dispatched_at
        model.locked_at = None
        model.last_error = None
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_outbox_dto(model)

    async def mark_outbox_failed(
        self,
        outbox_id: UUID,
        *,
        last_error: str,
        retryable: bool,
    ) -> RepoSyncOutboxDTO:
        result = await self._session.execute(select(RepoSyncOutboxModel).where(RepoSyncOutboxModel.id == outbox_id))
        model = result.scalar_one()
        model.status = "pending" if retryable else "failed"
        model.locked_at = None
        model.last_error = last_error
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_outbox_dto(model)

    async def has_active_outbox(self, repo_sync_id: UUID) -> bool:
        result = await self._session.execute(
            select(RepoSyncOutboxModel.id)
            .where(
                RepoSyncOutboxModel.repo_sync_id == repo_sync_id,
                RepoSyncOutboxModel.status != "dispatched",
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

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
            include_paths=list(model.include_paths or []),
            exclude_paths=list(model.exclude_paths or []),
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

    @staticmethod
    def _to_outbox_dto(model: RepoSyncOutboxModel) -> RepoSyncOutboxDTO:
        return RepoSyncOutboxDTO(
            id=model.id,
            repo_sync_id=model.repo_sync_id,
            document_id=model.document_id,
            task_name=model.task_name,
            status=model.status,
            attempts=model.attempts,
            locked_at=model.locked_at,
            last_error=model.last_error,
            dispatched_at=model.dispatched_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
