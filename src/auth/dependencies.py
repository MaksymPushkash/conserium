from fastapi import Depends
from redis.asyncio import Redis

from src.auth.jwt_service import JWTService
from src.auth.oauth_clients import GithubOAuthClient, GoogleOAuthClient
from src.auth.password_hasher import BcryptPasswordHasher
from src.auth.service import (
    AuthSessionService,
    OAuthLoginCompleter,
    RefreshTokenRotator,
    UserAuthenticator,
    UserRegistrar,
)
from src.kit.cache.redis import get_redis
from src.kit.cache.redis_cache import RedisCache
from src.postgres import AsyncSession, get_db_session
from src.settings import settings
from src.users.repository import UserRepository


def get_cache(redis: Redis = Depends(get_redis)) -> RedisCache:
    return RedisCache(redis)


def get_user_repository(session: AsyncSession = Depends(get_db_session)) -> UserRepository:
    return UserRepository.from_session(session)


def get_jwt_service() -> JWTService:
    return JWTService()


def get_user_registrar(
    session: AsyncSession = Depends(get_db_session),
    user_repo: UserRepository = Depends(get_user_repository),
    jwt_service: JWTService = Depends(get_jwt_service),
    cache: RedisCache = Depends(get_cache),
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
    jwt_service: JWTService = Depends(get_jwt_service),
    cache: RedisCache = Depends(get_cache),
) -> UserAuthenticator:
    return UserAuthenticator(
        user_repo,
        BcryptPasswordHasher(),
        jwt_service,
        cache,
        refresh_token_ttl_seconds=_refresh_token_ttl_seconds(),
    )


def get_refresh_token_rotator(
    jwt_service: JWTService = Depends(get_jwt_service),
    cache: RedisCache = Depends(get_cache),
) -> RefreshTokenRotator:
    return RefreshTokenRotator(jwt_service, cache, refresh_token_ttl_seconds=_refresh_token_ttl_seconds())


def get_auth_session_service(cache: RedisCache = Depends(get_cache)) -> AuthSessionService:
    return AuthSessionService(cache)


def get_oauth_login_completer(
    session: AsyncSession = Depends(get_db_session),
    user_repo: UserRepository = Depends(get_user_repository),
    jwt_service: JWTService = Depends(get_jwt_service),
    cache: RedisCache = Depends(get_cache),
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
    return GoogleOAuthClient(client_id=settings.GOOGLE_CLIENT_ID, client_secret=settings.GOOGLE_CLIENT_SECRET)


def get_github_oauth_client() -> GithubOAuthClient:
    return GithubOAuthClient(client_id=settings.GITHUB_CLIENT_ID, client_secret=settings.GITHUB_CLIENT_SECRET)


def _refresh_token_ttl_seconds() -> int:
    return settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
