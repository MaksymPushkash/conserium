import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.dtos.auth_dtos import CompleteOAuthLoginDTO, LoginDTO, OAuthProfileDTO, RefreshDTO, RegisterDTO
from src.application.ports.auth.oauth_provider import IOAuthProviderClient
from src.application.use_cases.auth.complete_oauth_login_use_case import CompleteOAuthLoginUseCase
from src.application.use_cases.auth.login_use_case import LoginUserUseCase
from src.application.use_cases.auth.refresh_token_use_case import RefreshTokenUseCase
from src.application.use_cases.auth.register_use_case import RegisterUserUseCase
from src.domain.entities.user_entity import UserEntity
from src.domain.exceptions import (
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    InvalidTokenException,
    UserInactiveException,
)
from src.domain.value_objects.email import Email

REFRESH_TTL = 30 * 24 * 3600  # 30 days in seconds


@pytest.fixture
def mock_uow():
    uow = AsyncMock()
    uow.user_repo = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    return uow


@pytest.fixture
def mock_password_hasher():
    hasher = MagicMock()
    hasher.hash.return_value = "$2b$12$hashed"
    hasher.verify.return_value = True
    return hasher


@pytest.fixture
def mock_jwt_service():
    service = MagicMock()
    service.generate_access_token.return_value = "access-token-123"
    service.generate_refresh_token.return_value = "refresh-token-456"
    service.verify_access_token.return_value = uuid.uuid4()
    service.verify_refresh_token.return_value = uuid.uuid4()
    return service


@pytest.fixture
def mock_cache():
    cache = AsyncMock()
    cache.get.return_value = None
    cache.get_del.return_value = None
    cache.set.return_value = None
    cache.set_if_absent.return_value = True
    cache.delete.return_value = None
    return cache


def _make_user_entity(*, is_active: bool = True) -> UserEntity:
    from datetime import UTC, datetime

    return UserEntity(
        id=uuid.uuid4(),
        email=Email(value="user@example.com"),
        password="$2b$12$hashedpassword",
        display_name="Test",
        is_active=is_active,
        created_at=datetime.now(UTC),
        updated_at=None,
    )


class _FakeOAuthProvider(IOAuthProviderClient):
    def __init__(self, profile: OAuthProfileDTO) -> None:
        self.profile = profile

    def authorization_url(self, *, redirect_uri: str, state: str) -> str:
        return f"https://provider.example/auth?redirect_uri={redirect_uri}&state={state}"

    async def fetch_user_profile(self, *, code: str, redirect_uri: str) -> OAuthProfileDTO:
        return self.profile


class TestRegisterUserUseCase:
    async def test_successful_registration(self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache):
        mock_uow.user_repo.exists_by_email.return_value = False

        use_case = RegisterUserUseCase(
            mock_uow,
            mock_password_hasher,
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        result = await use_case(RegisterDTO(email="new@example.com", password="securepass123"))

        assert result.access_token == "access-token-123"
        assert result.refresh_token == "refresh-token-456"
        mock_uow.user_repo.create.assert_awaited_once()
        mock_uow.commit.assert_awaited_once()
        mock_password_hasher.hash.assert_called_once_with("securepass123")
        mock_cache.set.assert_awaited_once()

    async def test_registration_duplicate_email_raises(
        self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache
    ):
        mock_uow.user_repo.exists_by_email.return_value = True

        use_case = RegisterUserUseCase(
            mock_uow,
            mock_password_hasher,
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        with pytest.raises(EmailAlreadyExistsException):
            await use_case(RegisterDTO(email="existing@example.com", password="securepass123"))

        mock_uow.user_repo.create.assert_not_awaited()
        mock_uow.commit.assert_not_awaited()

    async def test_registration_with_display_name(self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache):
        mock_uow.user_repo.exists_by_email.return_value = False

        use_case = RegisterUserUseCase(
            mock_uow,
            mock_password_hasher,
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        result = await use_case(
            RegisterDTO(
                email="new@example.com",
                password="securepass123",
                display_name="John Doe",
            )
        )

        assert result.access_token == "access-token-123"
        mock_uow.user_repo.create.assert_awaited_once()

    async def test_refresh_token_stored_in_cache(self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache):
        mock_uow.user_repo.exists_by_email.return_value = False

        use_case = RegisterUserUseCase(
            mock_uow,
            mock_password_hasher,
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        await use_case(RegisterDTO(email="new@example.com", password="securepass123"))

        mock_cache.set.assert_awaited_once()
        call_kwargs = mock_cache.set.call_args
        assert call_kwargs.kwargs["key"] == "refresh:refresh-token-456"
        assert call_kwargs.kwargs["ttl"] == REFRESH_TTL


class TestLoginUserUseCase:
    async def test_successful_login(self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache):
        user = _make_user_entity()
        mock_uow.user_repo.get_by_email.return_value = user

        use_case = LoginUserUseCase(
            mock_uow,
            mock_password_hasher,
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        result = await use_case(LoginDTO(email="user@example.com", password="password"))

        assert result.access_token == "access-token-123"
        assert result.refresh_token == "refresh-token-456"
        mock_password_hasher.verify.assert_called_once()

    async def test_login_user_not_found_raises(self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache):
        mock_uow.user_repo.get_by_email.return_value = None

        use_case = LoginUserUseCase(
            mock_uow,
            mock_password_hasher,
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        with pytest.raises(InvalidCredentialsException):
            await use_case(LoginDTO(email="nonexistent@example.com", password="password"))

    async def test_login_wrong_password_raises(self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache):
        user = _make_user_entity()
        mock_uow.user_repo.get_by_email.return_value = user
        mock_password_hasher.verify.return_value = False

        use_case = LoginUserUseCase(
            mock_uow,
            mock_password_hasher,
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        with pytest.raises(InvalidCredentialsException):
            await use_case(LoginDTO(email="user@example.com", password="wrong"))

    async def test_login_inactive_user_raises(self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache):
        user = _make_user_entity(is_active=False)
        mock_uow.user_repo.get_by_email.return_value = user

        use_case = LoginUserUseCase(
            mock_uow,
            mock_password_hasher,
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        with pytest.raises(UserInactiveException):
            await use_case(LoginDTO(email="user@example.com", password="password"))


class TestCompleteOAuthLoginUseCase:
    async def test_creates_user_and_issues_tokens(
        self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache
    ):
        mock_uow.user_repo.get_by_email.return_value = None
        provider = _FakeOAuthProvider(OAuthProfileDTO(email="oauth@example.com", display_name="OAuth User"))

        use_case = CompleteOAuthLoginUseCase(
            mock_uow,
            mock_password_hasher,
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        result = await use_case(
            CompleteOAuthLoginDTO(code="oauth-code", redirect_uri="https://api.example/callback"),
            provider,
        )

        assert result.access_token == "access-token-123"
        assert result.refresh_token == "refresh-token-456"
        mock_uow.user_repo.get_by_email.assert_awaited_once_with("oauth@example.com")
        mock_uow.user_repo.create.assert_awaited_once()
        mock_uow.commit.assert_awaited_once()
        mock_password_hasher.hash.assert_called_once()
        mock_cache.set.assert_awaited_once()

    async def test_existing_user_issues_tokens_without_creating_user(
        self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache
    ):
        existing_user = _make_user_entity()
        mock_uow.user_repo.get_by_email.return_value = existing_user
        provider = _FakeOAuthProvider(OAuthProfileDTO(email="user@example.com", display_name="OAuth User"))

        use_case = CompleteOAuthLoginUseCase(
            mock_uow,
            mock_password_hasher,
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        result = await use_case(
            CompleteOAuthLoginDTO(code="oauth-code", redirect_uri="https://api.example/callback"),
            provider,
        )

        assert result.access_token == "access-token-123"
        mock_uow.user_repo.create.assert_not_awaited()
        mock_uow.commit.assert_not_awaited()
        mock_password_hasher.hash.assert_not_called()
        mock_cache.set.assert_awaited_once()

    async def test_inactive_existing_user_raises(
        self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache
    ):
        mock_uow.user_repo.get_by_email.return_value = _make_user_entity(is_active=False)
        provider = _FakeOAuthProvider(OAuthProfileDTO(email="user@example.com", display_name="OAuth User"))

        use_case = CompleteOAuthLoginUseCase(
            mock_uow,
            mock_password_hasher,
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )

        with pytest.raises(UserInactiveException):
            await use_case(
                CompleteOAuthLoginDTO(code="oauth-code", redirect_uri="https://api.example/callback"),
                provider,
            )


class TestRefreshTokenUseCase:
    async def test_successful_refresh(self, mock_jwt_service, mock_cache):
        user_id = uuid.uuid4()
        mock_jwt_service.verify_refresh_token.return_value = user_id
        mock_cache.get_del.return_value = str(user_id)

        use_case = RefreshTokenUseCase(
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        result = await use_case(RefreshDTO(refresh_token="old-refresh-token"))

        assert result.access_token == "access-token-123"
        assert result.refresh_token == "refresh-token-456"
        mock_jwt_service.verify_refresh_token.assert_called_once_with("old-refresh-token")
        mock_jwt_service.generate_access_token.assert_called_once_with(user_id)
        mock_jwt_service.generate_refresh_token.assert_called_once_with(user_id)
        mock_cache.get_del.assert_awaited_once_with("refresh:old-refresh-token")
        mock_cache.set.assert_awaited_once()

    async def test_refresh_missing_cache_entry_raises(self, mock_jwt_service, mock_cache):
        user_id = uuid.uuid4()
        mock_jwt_service.verify_refresh_token.return_value = user_id
        mock_cache.get.return_value = None

        use_case = RefreshTokenUseCase(
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        with pytest.raises(InvalidTokenException):
            await use_case(RefreshDTO(refresh_token="expired-cache-token"))

        mock_jwt_service.verify_refresh_token.assert_called_once_with("expired-cache-token")
        mock_cache.get_del.assert_awaited_once_with("refresh:expired-cache-token")

    async def test_refresh_rotates_token(self, mock_jwt_service, mock_cache):
        """Ensure refresh token rotation: old deleted, new stored."""
        user_id = uuid.uuid4()
        mock_jwt_service.verify_refresh_token.return_value = user_id
        mock_cache.get_del.return_value = str(user_id)

        use_case = RefreshTokenUseCase(
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        await use_case(RefreshDTO(refresh_token="old-token"))

        mock_cache.get_del.assert_awaited_once_with("refresh:old-token")

        set_call = mock_cache.set.call_args
        assert set_call.kwargs["key"] == "refresh:refresh-token-456"

    async def test_refresh_access_token_rejected(self, mock_jwt_service, mock_cache):
        mock_jwt_service.verify_refresh_token.side_effect = InvalidTokenException("not a refresh token")

        use_case = RefreshTokenUseCase(
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )

        with pytest.raises(InvalidTokenException):
            await use_case(RefreshDTO(refresh_token="access-token"))

        mock_jwt_service.verify_refresh_token.assert_called_once_with("access-token")
        mock_cache.get_del.assert_not_awaited()

    async def test_refresh_corrupted_cache_user_id_raises(self, mock_jwt_service, mock_cache):
        mock_jwt_service.verify_refresh_token.return_value = uuid.uuid4()
        mock_cache.get.return_value = "not-a-uuid"

        use_case = RefreshTokenUseCase(
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )

        with pytest.raises(InvalidTokenException):
            await use_case(RefreshDTO(refresh_token="refresh-token"))

        mock_cache.get_del.assert_awaited_once_with("refresh:refresh-token")

    async def test_refresh_cache_subject_mismatch_raises(self, mock_jwt_service, mock_cache):
        mock_jwt_service.verify_refresh_token.return_value = uuid.uuid4()
        mock_cache.get.return_value = str(uuid.uuid4())

        use_case = RefreshTokenUseCase(
            mock_jwt_service,
            mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )

        with pytest.raises(InvalidTokenException):
            await use_case(RefreshDTO(refresh_token="refresh-token"))

        mock_cache.get_del.assert_awaited_once_with("refresh:refresh-token")
