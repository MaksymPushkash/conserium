from collections.abc import AsyncIterator

from dishka import Provider, Scope, make_async_container, provide
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.application.interfaces.cache import ICache
from src.application.interfaces.jwt_service import IJWTService
from src.application.interfaces.password_hasher import IPasswordHasher
from src.application.interfaces.text_chunker import ITextChunker
from src.application.interfaces.unit_of_work import IUnitOfWork
from src.application.use_cases.auth.login_use_case import LoginUserUseCase
from src.application.use_cases.auth.refresh_token_use_case import RefreshTokenUseCase
from src.application.use_cases.auth.register_use_case import RegisterUserUseCase
from src.application.use_cases.documents.create_document_use_case import CreateDocumentUseCase
from src.application.use_cases.documents.delete_document_use_case import DeleteDocumentUseCase
from src.application.use_cases.documents.get_document_use_case import GetDocumentUseCase
from src.application.use_cases.documents.ingest_text_document_use_case import IngestTextDocumentUseCase
from src.application.use_cases.documents.list_documents_use_case import ListDocumentsUseCase
from src.core.config import settings
from src.infrastructure.auth.jwt_service import JWTService
from src.infrastructure.auth.password_hasher import BcryptPasswordHasher
from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from src.infrastructure.text_processing import SimpleTextChunker


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

    @provide(scope=Scope.APP)
    async def get_redis(self) -> AsyncIterator[Redis]:
        redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)
        yield redis
        await redis.aclose()

    @provide(scope=Scope.APP)
    def get_jwt_service(self) -> IJWTService:
        return JWTService()

    @provide(scope=Scope.APP)
    def get_password_hasher(self) -> IPasswordHasher:
        return BcryptPasswordHasher()

    @provide(scope=Scope.APP)
    def get_cache(self, redis: Redis) -> ICache:
        return RedisCache(redis)

    @provide(scope=Scope.APP)
    def get_text_chunker(self) -> ITextChunker:
        return SimpleTextChunker()

    @provide(scope=Scope.REQUEST)
    def get_register_use_case(
        self,
        uow: IUnitOfWork,
        password_hasher: IPasswordHasher,
        jwt_service: IJWTService,
        cache: ICache,
    ) -> RegisterUserUseCase:
        return RegisterUserUseCase(
            uow,
            password_hasher,
            jwt_service,
            cache,
            refresh_token_ttl_seconds=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        )

    @provide(scope=Scope.REQUEST)
    def get_login_use_case(
        self,
        uow: IUnitOfWork,
        password_hasher: IPasswordHasher,
        jwt_service: IJWTService,
        cache: ICache,
    ) -> LoginUserUseCase:
        return LoginUserUseCase(
            uow,
            password_hasher,
            jwt_service,
            cache,
            refresh_token_ttl_seconds=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        )

    @provide(scope=Scope.REQUEST)
    def get_refresh_use_case(
        self,
        jwt_service: IJWTService,
        cache: ICache,
    ) -> RefreshTokenUseCase:
        return RefreshTokenUseCase(
            jwt_service,
            cache,
            refresh_token_ttl_seconds=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        )

    @provide(scope=Scope.REQUEST)
    def get_create_document_use_case(self, uow: IUnitOfWork) -> CreateDocumentUseCase:
        return CreateDocumentUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_list_documents_use_case(self, uow: IUnitOfWork) -> ListDocumentsUseCase:
        return ListDocumentsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_get_document_use_case(self, uow: IUnitOfWork) -> GetDocumentUseCase:
        return GetDocumentUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_delete_document_use_case(self, uow: IUnitOfWork) -> DeleteDocumentUseCase:
        return DeleteDocumentUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_ingest_text_document_use_case(
        self,
        uow: IUnitOfWork,
        text_chunker: ITextChunker,
    ) -> IngestTextDocumentUseCase:
        return IngestTextDocumentUseCase(uow, text_chunker)


container = make_async_container(AppProvider())
