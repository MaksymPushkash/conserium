from collections.abc import AsyncIterator

from dishka import Provider, Scope, make_async_container, provide
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.application.interfaces.user_repository import IUserRepository
from src.core.config import settings
from src.infrastructure.database.repositories.user_repository import SQLAlchemyUserRepository


class AppProvider(Provider):

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
    def get_session_factory(self, engine: AsyncEngine) -> async_sessionmaker:
        return async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @provide(scope=Scope.REQUEST)
    async def get_session(
        self, factory: async_sessionmaker
    ) -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    @provide(scope=Scope.REQUEST)
    def get_user_repository(self, session: AsyncSession) -> IUserRepository:
        return SQLAlchemyUserRepository(session)


container = make_async_container(AppProvider())