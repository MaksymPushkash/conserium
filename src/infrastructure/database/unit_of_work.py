from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.infrastructure.database.repositories.chat_repository import SQLAlchemyChatRepository
from src.infrastructure.database.repositories.chunk_repository import SQLAlchemyChunkRepository
from src.infrastructure.database.repositories.collection_repository import SQLAlchemyCollectionRepository
from src.infrastructure.database.repositories.collection_share_repository import SQLAlchemyCollectionShareRepository
from src.infrastructure.database.repositories.conflict_repository import SQLAlchemyConflictRepository
from src.infrastructure.database.repositories.document_activity_repository import SQLAlchemyDocumentActivityRepository
from src.infrastructure.database.repositories.document_repository import SQLAlchemyDocumentRepository
from src.infrastructure.database.repositories.external_connection_repository import (
    SQLAlchemyExternalConnectionRepository,
)
from src.infrastructure.database.repositories.knowledge_graph_repository import SQLAlchemyKnowledgeGraphRepository
from src.infrastructure.database.repositories.learning_goal_repository import SQLAlchemyLearningGoalRepository
from src.infrastructure.database.repositories.note_version_repository import SQLAlchemyNoteVersionRepository
from src.infrastructure.database.repositories.repo_sync_repository import SQLAlchemyRepoSyncRepository
from src.infrastructure.database.repositories.search_query_repository import SQLAlchemySearchQueryRepository
from src.infrastructure.database.repositories.stats_repository import SQLAlchemyStatsRepository
from src.infrastructure.database.repositories.topic_repository import SQLAlchemyTopicRepository
from src.infrastructure.database.repositories.user_repository import SQLAlchemyUserRepository

if TYPE_CHECKING:
    from types import TracebackType

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.application.ports.persistence.chat_repository import IChatRepository
    from src.application.ports.persistence.chunk_repository import IChunkRepository
    from src.application.ports.persistence.collection_repository import ICollectionRepository
    from src.application.ports.persistence.collection_share_repository import ICollectionShareRepository
    from src.application.ports.persistence.conflict_repository import IConflictRepository
    from src.application.ports.persistence.document_activity_repository import IDocumentActivityRepository
    from src.application.ports.persistence.document_repository import IDocumentRepository
    from src.application.ports.persistence.external_connection_repository import IExternalConnectionRepository
    from src.application.ports.persistence.knowledge_graph_repository import IKnowledgeGraphRepository
    from src.application.ports.persistence.learning_goal_repository import ILearningGoalRepository
    from src.application.ports.persistence.note_version_repository import INoteVersionRepository
    from src.application.ports.persistence.repo_sync_repository import IRepoSyncRepository
    from src.application.ports.persistence.search_query_repository import ISearchQueryRepository
    from src.application.ports.persistence.stats_repository import IStatsRepository
    from src.application.ports.persistence.topic_repository import ITopicRepository
    from src.application.ports.persistence.user_repository import IUserRepository


class SQLAlchemyUnitOfWork(IUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.user_repo: IUserRepository = SQLAlchemyUserRepository(session)
        self.chat_repo: IChatRepository = SQLAlchemyChatRepository(session)
        self.collection_repo: ICollectionRepository = SQLAlchemyCollectionRepository(session)
        self.collection_share_repo: ICollectionShareRepository = SQLAlchemyCollectionShareRepository(session)
        self.conflict_repo: IConflictRepository = SQLAlchemyConflictRepository(session)
        self.document_repo: IDocumentRepository = SQLAlchemyDocumentRepository(session)
        self.document_activity_repo: IDocumentActivityRepository = SQLAlchemyDocumentActivityRepository(session)
        self.external_connection_repo: IExternalConnectionRepository = SQLAlchemyExternalConnectionRepository(session)
        self.chunk_repo: IChunkRepository = SQLAlchemyChunkRepository(session)
        self.note_version_repo: INoteVersionRepository = SQLAlchemyNoteVersionRepository(session)
        self.repo_sync_repo: IRepoSyncRepository = SQLAlchemyRepoSyncRepository(session)
        self.search_query_repo: ISearchQueryRepository = SQLAlchemySearchQueryRepository(session)
        self.stats_repo: IStatsRepository = SQLAlchemyStatsRepository(session)
        self.topic_repo: ITopicRepository = SQLAlchemyTopicRepository(session)
        self.knowledge_graph_repo: IKnowledgeGraphRepository = SQLAlchemyKnowledgeGraphRepository(session)
        self.learning_goal_repo: ILearningGoalRepository = SQLAlchemyLearningGoalRepository(session)

    async def __aenter__(self) -> SQLAlchemyUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type:
            await self.rollback()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
