from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from src.compare.repository import CompareRepository
from src.drafts.repository import DraftRecord, DraftRepository
from src.models.collection import CollectionModel
from src.models.shared_workspace import WorkspaceMemberModel
from src.query.repository import SearchQueryRepository, SearchQuerySummaryRecord

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.compare.schemas import CompareResult


@dataclass(frozen=True, slots=True)
class CollectionWorkspaceRecentActivity:
    questions: list[SearchQuerySummaryRecord]
    drafts: list[DraftRecord]
    comparisons: list[CompareResult]


class CollectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> CollectionRepository:
        return cls(session)

    async def get_by_id(self, collection_id: UUID) -> CollectionModel | None:
        result = await self._session.execute(select(CollectionModel).where(CollectionModel.id == collection_id))
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: UUID, *, limit: int = 100, offset: int = 0) -> list[CollectionModel]:
        result = await self._session.execute(
            select(CollectionModel)
            .where(CollectionModel.user_id == user_id)
            .order_by(CollectionModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_visible_by_user_id(self, user_id: UUID, *, limit: int = 100, offset: int = 0) -> list[CollectionModel]:
        workspace_collection_ids = (
            select(CollectionModel.id)
            .join(
                WorkspaceMemberModel,
                WorkspaceMemberModel.workspace_id == CollectionModel.workspace_id,
            )
            .where(WorkspaceMemberModel.user_id == user_id)
        )
        result = await self._session.execute(
            select(CollectionModel)
            .where((CollectionModel.user_id == user_id) | CollectionModel.id.in_(workspace_collection_ids))
            .order_by(CollectionModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_visible_by_workspace_id(
        self,
        user_id: UUID,
        workspace_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CollectionModel]:
        result = await self._session.execute(
            select(CollectionModel)
            .outerjoin(
                WorkspaceMemberModel,
                WorkspaceMemberModel.workspace_id == CollectionModel.workspace_id,
            )
            .where(
                CollectionModel.workspace_id == workspace_id,
                (CollectionModel.user_id == user_id) | (WorkspaceMemberModel.user_id == user_id),
            )
            .order_by(CollectionModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().unique().all())

    async def create(self, collection: CollectionModel) -> None:
        self._session.add(collection)

    async def update(self, collection: CollectionModel) -> None:
        self._session.add(collection)

    async def delete(self, collection_id: UUID) -> None:
        await self._session.execute(delete(CollectionModel).where(CollectionModel.id == collection_id))

    async def count_by_user_id(self, user_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(CollectionModel).where(CollectionModel.user_id == user_id)
        )
        return result.scalar_one()

    async def count_visible_by_user_id(self, user_id: UUID) -> int:
        workspace_collection_ids = (
            select(CollectionModel.id)
            .join(
                WorkspaceMemberModel,
                WorkspaceMemberModel.workspace_id == CollectionModel.workspace_id,
            )
            .where(WorkspaceMemberModel.user_id == user_id)
        )
        result = await self._session.execute(
            select(func.count())
            .select_from(CollectionModel)
            .where((CollectionModel.user_id == user_id) | CollectionModel.id.in_(workspace_collection_ids))
        )
        return result.scalar_one()

    async def count_visible_by_workspace_id(self, user_id: UUID, workspace_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count(func.distinct(CollectionModel.id)))
            .select_from(CollectionModel)
            .outerjoin(
                WorkspaceMemberModel,
                WorkspaceMemberModel.workspace_id == CollectionModel.workspace_id,
            )
            .where(
                CollectionModel.workspace_id == workspace_id,
                (CollectionModel.user_id == user_id) | (WorkspaceMemberModel.user_id == user_id),
            )
        )
        return result.scalar_one()

class CollectionWorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._search_query_repo = SearchQueryRepository(session)
        self._draft_repo = DraftRepository(session)
        self._compare_repo = CompareRepository(session)

    @classmethod
    def from_session(cls, session: AsyncSession) -> CollectionWorkspaceRepository:
        return cls(session)

    async def get_recent_activity(
        self,
        *,
        user_id: UUID,
        collection_id: UUID,
        limit: int,
    ) -> CollectionWorkspaceRecentActivity:
        return CollectionWorkspaceRecentActivity(
            questions=await self._search_query_repo.list_recent_by_collection(
                user_id=user_id,
                collection_id=collection_id,
                limit=limit,
            ),
            drafts=await self._draft_repo.list_by_user_id(
                user_id=user_id,
                collection_id=collection_id,
                limit=limit,
            ),
            comparisons=await self._compare_repo.list_by_user_id(
                user_id=user_id,
                collection_id=collection_id,
                limit=limit,
            ),
        )


__all__ = [
    "CollectionRepository",
    "CollectionWorkspaceRecentActivity",
    "CollectionWorkspaceRepository",
]
