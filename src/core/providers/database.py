from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.core.config import settings
from src.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork


class DatabaseProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_engine(self) -> AsyncIterator[AsyncEngine]:
        engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        yield engine
        await engine.dispose()

    @provide(scope=Scope.APP)
    def get_session_factory(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @provide(scope=Scope.REQUEST)
    async def get_session(self, factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    @provide(scope=Scope.REQUEST)
    def get_unit_of_work(self, session: AsyncSession) -> IUnitOfWork:
        return SQLAlchemyUnitOfWork(session)
