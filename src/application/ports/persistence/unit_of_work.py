from abc import ABC, abstractmethod
from types import TracebackType

from src.application.ports.persistence.chunk_repository import IChunkRepository
from src.application.ports.persistence.document_repository import IDocumentRepository
from src.application.ports.persistence.user_repository import IUserRepository


class IUnitOfWork(ABC):
    user_repo: IUserRepository
    document_repo: IDocumentRepository
    chunk_repo: IChunkRepository

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
