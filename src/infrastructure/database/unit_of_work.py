from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.infrastructure.database.repositories.chunk_repository import SQLAlchemyChunkRepository
from src.infrastructure.database.repositories.document_repository import SQLAlchemyDocumentRepository
from src.infrastructure.database.repositories.user_repository import SQLAlchemyUserRepository

if TYPE_CHECKING:
    from types import TracebackType

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.application.ports.persistence.chunk_repository import IChunkRepository
    from src.application.ports.persistence.document_repository import IDocumentRepository
    from src.application.ports.persistence.user_repository import IUserRepository


class SQLAlchemyUnitOfWork(IUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.user_repo: IUserRepository = SQLAlchemyUserRepository(session)
        self.document_repo: IDocumentRepository = SQLAlchemyDocumentRepository(session)
        self.chunk_repo: IChunkRepository = SQLAlchemyChunkRepository(session)

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
