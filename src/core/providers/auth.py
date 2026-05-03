from dishka import Provider, Scope, provide

from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.auth.password_hasher import IPasswordHasher
from src.application.ports.cache.cache import ICache
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.auth.login_use_case import LoginUserUseCase
from src.application.use_cases.auth.refresh_token_use_case import RefreshTokenUseCase
from src.application.use_cases.auth.register_use_case import RegisterUserUseCase
from src.core.config import settings
from src.infrastructure.auth.jwt_service import JWTService
from src.infrastructure.auth.password_hasher import BcryptPasswordHasher


class AuthProvider(Provider):
    @provide(scope=Scope.APP)
    def get_jwt_service(self) -> IJWTService:
        return JWTService()

    @provide(scope=Scope.APP)
    def get_password_hasher(self) -> IPasswordHasher:
        return BcryptPasswordHasher()

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
