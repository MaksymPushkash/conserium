from abc import ABC, abstractmethod
from types import TracebackType

from src.application.ports.persistence.chat_repository import IChatRepository
from src.application.ports.persistence.chunk_repository import IChunkRepository
from src.application.ports.persistence.collection_repository import ICollectionRepository
from src.application.ports.persistence.document_activity_repository import IDocumentActivityRepository
from src.application.ports.persistence.document_repository import IDocumentRepository
from src.application.ports.persistence.note_version_repository import INoteVersionRepository
from src.application.ports.persistence.search_query_repository import ISearchQueryRepository
from src.application.ports.persistence.stats_repository import IStatsRepository
from src.application.ports.persistence.topic_repository import ITopicRepository
from src.application.ports.persistence.user_repository import IUserRepository


class IUnitOfWork(ABC):
    """Transaction boundary.

    Read-only blocks do not commit. Write blocks must call commit() explicitly.
    __aexit__ is responsible for cleanup/rollback, not implicit persistence.
    """

    user_repo: IUserRepository
    chat_repo: IChatRepository
    collection_repo: ICollectionRepository
    document_repo: IDocumentRepository
    document_activity_repo: IDocumentActivityRepository
    chunk_repo: IChunkRepository
    note_version_repo: INoteVersionRepository
    search_query_repo: ISearchQueryRepository
    stats_repo: IStatsRepository
    topic_repo: ITopicRepository

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
