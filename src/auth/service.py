import uuid
from uuid import UUID

from fastapi import Depends
from redis.asyncio import Redis

from src.auth.jwt_service import JWTService, JWTServiceProtocol
from src.auth.oauth_clients import GithubOAuthClient, GoogleOAuthClient, OAuthProviderClient
from src.auth.password_hasher import BcryptPasswordHasher, PasswordHasher
from src.auth.schemas import (
    CompleteOAuthLoginDTO,
    LoginDTO,
    LoginRequest,
    RefreshDTO,
    RegisterDTO,
    RegisterRequest,
    TokenResponse,
    TokenResponseDTO,
    UpdateUserPreferencesDTO,
)
from src.kit.cache.redis import get_redis
from src.kit.cache.redis_cache import RedisCache
from src.kit.exceptions import (
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    InvalidTokenException,
    ResourceNotFoundException,
)
from src.kit.ports.cache.cache import ICache
from src.models.user import UserModel
from src.postgres import AsyncSession, get_db_session
from src.settings import settings
from src.users.repository import UserRepository


class AuthTokenIssuer:
    def __init__(self, jwt_service: JWTServiceProtocol, cache: ICache, refresh_token_ttl_seconds: int) -> None:
        self._jwt_service = jwt_service
        self._cache = cache
        self._refresh_token_ttl_seconds = refresh_token_ttl_seconds

    async def _issue_tokens(self, user_id: UUID) -> TokenResponseDTO:
        access_token = self._jwt_service.generate_access_token(user_id)
        refresh_token = self._jwt_service.generate_refresh_token(user_id)
        await self._cache.set(
            key=f"refresh:{refresh_token}",
            value=str(user_id),
            ttl=self._refresh_token_ttl_seconds,
        )
        return TokenResponseDTO(access_token=access_token, refresh_token=refresh_token)


class UserRegistrar(AuthTokenIssuer):
    def __init__(
        self,
        user_repo: UserRepository,
        session: AsyncSession,
        password_hasher: PasswordHasher,
        jwt_service: JWTServiceProtocol,
        cache: ICache,
        refresh_token_ttl_seconds: int,
    ) -> None:
        super().__init__(jwt_service, cache, refresh_token_ttl_seconds)
        self._user_repo = user_repo
        self._session = session
        self._password_hasher = password_hasher

    async def __call__(self, dto: RegisterDTO) -> TokenResponseDTO:
        already_exists = await self._user_repo.exists_by_email(dto.email)
        if already_exists:
            raise EmailAlreadyExistsException(f"{dto.email} already registered")

        user = UserModel.create(
            id=uuid.uuid4(),
            email=dto.email,
            password=self._password_hasher.hash(dto.password),
            display_name=dto.display_name,
        )

        await self._user_repo.create(user)
        await self._session.flush()

        return await self._issue_tokens(user.id)


class UserAuthenticator(AuthTokenIssuer):
    def __init__(
        self,
        user_repo: UserRepository,
        password_hasher: PasswordHasher,
        jwt_service: JWTServiceProtocol,
        cache: ICache,
        refresh_token_ttl_seconds: int,
    ) -> None:
        super().__init__(jwt_service, cache, refresh_token_ttl_seconds)
        self._user_repo = user_repo
        self._password_hasher = password_hasher

    async def __call__(self, dto: LoginDTO) -> TokenResponseDTO:
        user = await self._user_repo.get_by_email(dto.email)

        if user is None:
            raise InvalidCredentialsException("invalid email or password")

        if not self._password_hasher.verify(dto.password, str(user.password)):
            raise InvalidCredentialsException("invalid email or password")

        user.ensure_active()

        return await self._issue_tokens(user.id)


class RefreshTokenRotator(AuthTokenIssuer):
    def __init__(
        self,
        jwt_service: JWTServiceProtocol,
        cache: ICache,
        refresh_token_ttl_seconds: int,
    ) -> None:
        super().__init__(jwt_service, cache, refresh_token_ttl_seconds)

    async def __call__(self, dto: RefreshDTO) -> TokenResponseDTO:
        token_user_id = self._jwt_service.verify_refresh_token(dto.refresh_token)
        key = f"refresh:{dto.refresh_token}"

        cached_user_id = await self._cache.get_del(key)
        if cached_user_id is None:
            raise InvalidTokenException("refresh token not found or expired")

        try:
            cache_user_id = uuid.UUID(cached_user_id)
        except ValueError as e:
            raise InvalidTokenException("refresh token session is corrupted") from e

        if cache_user_id != token_user_id:
            raise InvalidTokenException("refresh token session does not match token subject")

        return await self._issue_tokens(token_user_id)


class AuthSessionService:
    def __init__(self, cache: ICache) -> None:
        self._cache = cache

    async def logout(self, dto: RefreshDTO) -> None:
        await self._cache.delete(f"refresh:{dto.refresh_token}")

    async def logout_all(self, user_id: object) -> int:
        return await self._cache.delete_by_value_prefix("refresh:", str(user_id))


class OAuthLoginCompleter(AuthTokenIssuer):
    def __init__(
        self,
        user_repo: UserRepository,
        session: AsyncSession,
        password_hasher: PasswordHasher,
        jwt_service: JWTServiceProtocol,
        cache: ICache,
        refresh_token_ttl_seconds: int,
    ) -> None:
        super().__init__(jwt_service, cache, refresh_token_ttl_seconds)
        self._user_repo = user_repo
        self._session = session
        self._password_hasher = password_hasher

    async def __call__(self, dto: CompleteOAuthLoginDTO, provider: OAuthProviderClient) -> TokenResponseDTO:
        profile = await provider.fetch_user_profile(code=dto.code, redirect_uri=dto.redirect_uri)

        user = await self._user_repo.get_by_email(profile.email)
        if user is None:
            user = UserModel.create(
                id=uuid.uuid4(),
                email=profile.email,
                password=self._password_hasher.hash(uuid.uuid4().hex),
                display_name=profile.display_name,
            )
            await self._user_repo.create(user)
            await self._session.flush()
        else:
            user.ensure_active()

        return await self._issue_tokens(user.id)


class AccountDeleter:
    def __init__(self, user_repo: UserRepository, session: AsyncSession) -> None:
        self._user_repo = user_repo
        self._session = session

    async def __call__(self, user_id: UUID) -> None:
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundException("user not found")
        await self._user_repo.delete(user_id)
        await self._session.flush()


class UserPreferencesUpdater:
    def __init__(self, user_repo: UserRepository, session: AsyncSession) -> None:
        self._user_repo = user_repo
        self._session = session

    async def __call__(self, dto: UpdateUserPreferencesDTO) -> UserModel:
        user = await self._user_repo.get_by_id(dto.user_id)
        if user is None:
            raise ResourceNotFoundException("user not found")
        user.update_preferences(dto.preferences)
        await self._user_repo.update(user)
        await self._session.flush()
        return user


def get_cache(redis: Redis = Depends(get_redis)) -> ICache:
    return RedisCache(redis)


def get_user_repository(session: AsyncSession = Depends(get_db_session)) -> UserRepository:
    return UserRepository.from_session(session)


def get_jwt_service() -> JWTServiceProtocol:
    return JWTService()


def get_user_registrar(
    session: AsyncSession = Depends(get_db_session),
    user_repo: UserRepository = Depends(get_user_repository),
    jwt_service: JWTServiceProtocol = Depends(get_jwt_service),
    cache: ICache = Depends(get_cache),
) -> UserRegistrar:
    return UserRegistrar(
        user_repo,
        session,
        BcryptPasswordHasher(),
        jwt_service,
        cache,
        refresh_token_ttl_seconds=_refresh_token_ttl_seconds(),
    )


def get_user_authenticator(
    user_repo: UserRepository = Depends(get_user_repository),
    jwt_service: JWTServiceProtocol = Depends(get_jwt_service),
    cache: ICache = Depends(get_cache),
) -> UserAuthenticator:
    return UserAuthenticator(
        user_repo,
        BcryptPasswordHasher(),
        jwt_service,
        cache,
        refresh_token_ttl_seconds=_refresh_token_ttl_seconds(),
    )


def get_refresh_token_rotator(
    jwt_service: JWTServiceProtocol = Depends(get_jwt_service),
    cache: ICache = Depends(get_cache),
) -> RefreshTokenRotator:
    return RefreshTokenRotator(
        jwt_service,
        cache,
        refresh_token_ttl_seconds=_refresh_token_ttl_seconds(),
    )


def get_auth_session_service(cache: ICache = Depends(get_cache)) -> AuthSessionService:
    return AuthSessionService(cache)


def get_oauth_login_completer(
    session: AsyncSession = Depends(get_db_session),
    user_repo: UserRepository = Depends(get_user_repository),
    jwt_service: JWTServiceProtocol = Depends(get_jwt_service),
    cache: ICache = Depends(get_cache),
) -> OAuthLoginCompleter:
    return OAuthLoginCompleter(
        user_repo,
        session,
        BcryptPasswordHasher(),
        jwt_service,
        cache,
        refresh_token_ttl_seconds=_refresh_token_ttl_seconds(),
    )


def get_google_oauth_client() -> GoogleOAuthClient:
    return GoogleOAuthClient(
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
    )


def get_github_oauth_client() -> GithubOAuthClient:
    return GithubOAuthClient(
        client_id=settings.GITHUB_CLIENT_ID,
        client_secret=settings.GITHUB_CLIENT_SECRET,
    )


def _refresh_token_ttl_seconds() -> int:
    return settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600


def to_register_dto(body: RegisterRequest) -> RegisterDTO:
    return RegisterDTO(email=body.email, password=body.password, display_name=body.display_name)


def to_login_dto(body: LoginRequest) -> LoginDTO:
    return LoginDTO(email=body.email, password=body.password)


def to_refresh_dto(refresh_token: str) -> RefreshDTO:
    return RefreshDTO(refresh_token=refresh_token)


def to_complete_oauth_login_dto(code: str, redirect_uri: str) -> CompleteOAuthLoginDTO:
    return CompleteOAuthLoginDTO(code=code, redirect_uri=redirect_uri)


def to_token_response(dto: TokenResponseDTO) -> TokenResponse:
    return TokenResponse(access_token=dto.access_token)




__all__ = [
    "AccountDeleter",
    "AuthSessionService",
    "AuthTokenIssuer",
    "OAuthLoginCompleter",
    "OAuthProviderClient",
    "RefreshTokenRotator",
    "UserAuthenticator",
    "UserPreferencesUpdater",
    "UserRegistrar",
    "get_auth_session_service",
    "get_github_oauth_client",
    "get_google_oauth_client",
    "get_oauth_login_completer",
    "get_refresh_token_rotator",
    "get_user_authenticator",
    "get_user_registrar",
    "get_user_repository",
    "to_complete_oauth_login_dto",
    "to_login_dto",
    "to_refresh_dto",
    "to_register_dto",
    "to_token_response",
]
