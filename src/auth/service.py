import uuid
from uuid import UUID

from src.auth.jwt_service import JWTService
from src.auth.oauth_clients import OAuthProvider
from src.auth.password_hasher import BcryptPasswordHasher
from src.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenPair,
    TokenResponse,
)
from src.kit.cache.redis_cache import RedisCache
from src.kit.exceptions import (
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    InvalidTokenException,
    ResourceNotFoundException,
)
from src.models.user import UserModel
from src.postgres import AsyncSession
from src.users.repository import UserRepository


class AuthTokenIssuer:
    def __init__(self, jwt_service: JWTService, cache: RedisCache, refresh_token_ttl_seconds: int) -> None:
        self._jwt_service = jwt_service
        self._cache = cache
        self._refresh_token_ttl_seconds = refresh_token_ttl_seconds

    async def _issue_tokens(self, user_id: UUID) -> TokenPair:
        access_token = self._jwt_service.generate_access_token(user_id)
        refresh_token = self._jwt_service.generate_refresh_token(user_id)
        await self._cache.set(
            key=f"refresh:{refresh_token}",
            value=str(user_id),
            ttl=self._refresh_token_ttl_seconds,
        )
        return TokenPair(access_token=access_token, refresh_token=refresh_token)


class UserRegistrar(AuthTokenIssuer):
    def __init__(
        self,
        user_repo: UserRepository,
        session: AsyncSession,
        password_hasher: BcryptPasswordHasher,
        jwt_service: JWTService,
        cache: RedisCache,
        refresh_token_ttl_seconds: int,
    ) -> None:
        super().__init__(jwt_service, cache, refresh_token_ttl_seconds)
        self._user_repo = user_repo
        self._session = session
        self._password_hasher = password_hasher

    async def __call__(self, request: RegisterRequest) -> TokenPair:
        already_exists = await self._user_repo.exists_by_email(request.email)
        if already_exists:
            raise EmailAlreadyExistsException(f"{request.email} already registered")

        user = UserModel.create(
            id=uuid.uuid4(),
            email=request.email,
            password=self._password_hasher.hash(request.password),
            display_name=request.display_name,
        )

        await self._user_repo.create(user)
        await self._session.flush()

        return await self._issue_tokens(user.id)


class UserAuthenticator(AuthTokenIssuer):
    def __init__(
        self,
        user_repo: UserRepository,
        password_hasher: BcryptPasswordHasher,
        jwt_service: JWTService,
        cache: RedisCache,
        refresh_token_ttl_seconds: int,
    ) -> None:
        super().__init__(jwt_service, cache, refresh_token_ttl_seconds)
        self._user_repo = user_repo
        self._password_hasher = password_hasher

    async def __call__(self, request: LoginRequest) -> TokenPair:
        user = await self._user_repo.get_by_email(request.email)

        if user is None:
            raise InvalidCredentialsException("invalid email or password")

        if not self._password_hasher.verify(request.password, str(user.password)):
            raise InvalidCredentialsException("invalid email or password")

        user.ensure_active()

        return await self._issue_tokens(user.id)


class RefreshTokenRotator(AuthTokenIssuer):
    def __init__(
        self,
        jwt_service: JWTService,
        cache: RedisCache,
        refresh_token_ttl_seconds: int,
    ) -> None:
        super().__init__(jwt_service, cache, refresh_token_ttl_seconds)

    async def __call__(self, refresh_token: str) -> TokenPair:
        token_user_id = self._jwt_service.verify_refresh_token(refresh_token)
        key = f"refresh:{refresh_token}"

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
    def __init__(self, cache: RedisCache) -> None:
        self._cache = cache

    async def logout(self, refresh_token: str) -> None:
        await self._cache.delete(f"refresh:{refresh_token}")

    async def logout_all(self, user_id: object) -> int:
        return await self._cache.delete_by_value_prefix("refresh:", str(user_id))


class OAuthLoginCompleter(AuthTokenIssuer):
    def __init__(
        self,
        user_repo: UserRepository,
        session: AsyncSession,
        password_hasher: BcryptPasswordHasher,
        jwt_service: JWTService,
        cache: RedisCache,
        refresh_token_ttl_seconds: int,
    ) -> None:
        super().__init__(jwt_service, cache, refresh_token_ttl_seconds)
        self._user_repo = user_repo
        self._session = session
        self._password_hasher = password_hasher

    async def __call__(self, *, code: str, redirect_uri: str, provider: OAuthProvider) -> TokenPair:
        profile = await provider.fetch_user_profile(code=code, redirect_uri=redirect_uri)

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

    async def __call__(self, *, user_id: UUID, preferences: dict[str, object]) -> UserModel:
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundException("user not found")
        user.update_preferences(preferences)
        await self._user_repo.update(user)
        await self._session.flush()
        return user


def to_token_response(tokens: TokenPair) -> TokenResponse:
    return TokenResponse(access_token=tokens.access_token)




__all__ = [
    "AccountDeleter",
    "AuthSessionService",
    "AuthTokenIssuer",
    "OAuthLoginCompleter",
    "RefreshTokenRotator",
    "UserAuthenticator",
    "UserPreferencesUpdater",
    "UserRegistrar",
    "to_token_response",
]
