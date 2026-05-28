from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.persistence.collection_workspace_repository import (
    CollectionWorkspaceRecentActivity,
    ICollectionWorkspaceRepository,
)
from src.infrastructure.database.repositories.compare_repository import SQLAlchemyCompareRepository
from src.infrastructure.database.repositories.draft_repository import SQLAlchemyDraftRepository
from src.infrastructure.database.repositories.search_query_repository import SQLAlchemySearchQueryRepository


class SQLAlchemyCollectionWorkspaceRepository(ICollectionWorkspaceRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._search_query_repo = SQLAlchemySearchQueryRepository(session)
        self._draft_repo = SQLAlchemyDraftRepository(session)
        self._compare_repo = SQLAlchemyCompareRepository(session)

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
