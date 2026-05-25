from abc import ABC, abstractmethod
from types import TracebackType

from src.application.ports.persistence.api_key_repository import IApiKeyRepository
from src.application.ports.persistence.chat_repository import IChatRepository
from src.application.ports.persistence.chunk_repository import IChunkRepository
from src.application.ports.persistence.collection_repository import ICollectionRepository
from src.application.ports.persistence.collection_share_repository import ICollectionShareRepository
from src.application.ports.persistence.compare_repository import ICompareRepository
from src.application.ports.persistence.conflict_repository import IConflictRepository
from src.application.ports.persistence.document_activity_repository import IDocumentActivityRepository
from src.application.ports.persistence.document_repository import IDocumentRepository
from src.application.ports.persistence.draft_repository import IDraftRepository
from src.application.ports.persistence.external_connection_repository import IExternalConnectionRepository
from src.application.ports.persistence.external_intake_repository import IExternalIntakeRepository
from src.application.ports.persistence.knowledge_graph_repository import IKnowledgeGraphRepository
from src.application.ports.persistence.learning_goal_repository import ILearningGoalRepository
from src.application.ports.persistence.note_version_repository import INoteVersionRepository
from src.application.ports.persistence.repo_sync_repository import IRepoSyncRepository
from src.application.ports.persistence.search_query_repository import ISearchQueryRepository
from src.application.ports.persistence.stats_repository import IStatsRepository
from src.application.ports.persistence.topic_repository import ITopicRepository
from src.application.ports.persistence.user_repository import IUserRepository


class IUnitOfWork(ABC):
    """Transaction boundary.

    Read-only blocks do not commit. Write blocks must call commit() explicitly.
    __aexit__ is responsible for cleanup/rollback, not implicit persistence.
    """

    api_key_repo: IApiKeyRepository
    user_repo: IUserRepository
    chat_repo: IChatRepository
    collection_repo: ICollectionRepository
    collection_share_repo: ICollectionShareRepository
    compare_repo: ICompareRepository
    conflict_repo: IConflictRepository
    document_repo: IDocumentRepository
    document_activity_repo: IDocumentActivityRepository
    draft_repo: IDraftRepository
    external_connection_repo: IExternalConnectionRepository
    external_intake_repo: IExternalIntakeRepository
    chunk_repo: IChunkRepository
    note_version_repo: INoteVersionRepository
    repo_sync_repo: IRepoSyncRepository
    search_query_repo: ISearchQueryRepository
    stats_repo: IStatsRepository
    topic_repo: ITopicRepository
    knowledge_graph_repo: IKnowledgeGraphRepository
    learning_goal_repo: ILearningGoalRepository

    @abstractmethod
    async def __aenter__(self) -> "IUnitOfWork": ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...
