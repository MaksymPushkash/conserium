import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.dtos.auth_dtos import LoginDTO, RefreshDTO, RegisterDTO
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
    return service


@pytest.fixture
def mock_cache():
    cache = AsyncMock()
    cache.get.return_value = None
    cache.set.return_value = None
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


class TestRegisterUserUseCase:

    async def test_successful_registration(self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache):
        mock_uow.user_repo.exists_by_email.return_value = False

        use_case = RegisterUserUseCase(
            mock_uow, mock_password_hasher, mock_jwt_service, mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        result = await use_case(RegisterDTO(email="new@example.com", password="securepass123"))

        assert result.access_token == "access-token-123"
        assert result.refresh_token == "refresh-token-456"
        mock_uow.user_repo.create.assert_awaited_once()
        mock_uow.commit.assert_awaited_once()
        mock_password_hasher.hash.assert_called_once_with("securepass123")
        mock_cache.set.assert_awaited_once()

    async def test_registration_duplicate_email_raises(self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache):
        mock_uow.user_repo.exists_by_email.return_value = True

        use_case = RegisterUserUseCase(
            mock_uow, mock_password_hasher, mock_jwt_service, mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        with pytest.raises(EmailAlreadyExistsException):
            await use_case(RegisterDTO(email="existing@example.com", password="securepass123"))

        mock_uow.user_repo.create.assert_not_awaited()
        mock_uow.commit.assert_not_awaited()

    async def test_registration_with_display_name(self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache):
        mock_uow.user_repo.exists_by_email.return_value = False

        use_case = RegisterUserUseCase(
            mock_uow, mock_password_hasher, mock_jwt_service, mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        result = await use_case(RegisterDTO(
            email="new@example.com",
            password="securepass123",
            display_name="John Doe",
        ))

        assert result.access_token == "access-token-123"
        mock_uow.user_repo.create.assert_awaited_once()

    async def test_refresh_token_stored_in_cache(self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache):
        mock_uow.user_repo.exists_by_email.return_value = False

        use_case = RegisterUserUseCase(
            mock_uow, mock_password_hasher, mock_jwt_service, mock_cache,
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
            mock_uow, mock_password_hasher, mock_jwt_service, mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        result = await use_case(LoginDTO(email="user@example.com", password="password"))

        assert result.access_token == "access-token-123"
        assert result.refresh_token == "refresh-token-456"
        mock_password_hasher.verify.assert_called_once()

    async def test_login_user_not_found_raises(self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache):
        mock_uow.user_repo.get_by_email.return_value = None

        use_case = LoginUserUseCase(
            mock_uow, mock_password_hasher, mock_jwt_service, mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        with pytest.raises(InvalidCredentialsException):
            await use_case(LoginDTO(email="nonexistent@example.com", password="password"))

    async def test_login_wrong_password_raises(self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache):
        user = _make_user_entity()
        mock_uow.user_repo.get_by_email.return_value = user
        mock_password_hasher.verify.return_value = False

        use_case = LoginUserUseCase(
            mock_uow, mock_password_hasher, mock_jwt_service, mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        with pytest.raises(InvalidCredentialsException):
            await use_case(LoginDTO(email="user@example.com", password="wrong"))

    async def test_login_inactive_user_raises(self, mock_uow, mock_password_hasher, mock_jwt_service, mock_cache):
        user = _make_user_entity(is_active=False)
        mock_uow.user_repo.get_by_email.return_value = user

        use_case = LoginUserUseCase(
            mock_uow, mock_password_hasher, mock_jwt_service, mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        with pytest.raises(UserInactiveException):
            await use_case(LoginDTO(email="user@example.com", password="password"))


class TestRefreshTokenUseCase:

    async def test_successful_refresh(self, mock_jwt_service, mock_cache):
        user_id = uuid.uuid4()
        mock_cache.get.return_value = str(user_id)

        use_case = RefreshTokenUseCase(
            mock_jwt_service, mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        result = await use_case(RefreshDTO(refresh_token="old-refresh-token"))

        assert result.access_token == "access-token-123"
        assert result.refresh_token == "refresh-token-456"
    
        mock_cache.delete.assert_awaited_once_with("refresh:old-refresh-token")
    
        mock_cache.set.assert_awaited_once()

    async def test_refresh_expired_token_raises(self, mock_jwt_service, mock_cache):
        mock_cache.get.return_value = None

        use_case = RefreshTokenUseCase(
            mock_jwt_service, mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        with pytest.raises(InvalidTokenException):
            await use_case(RefreshDTO(refresh_token="expired-token"))

    async def test_refresh_rotates_token(self, mock_jwt_service, mock_cache):
        """Ensure refresh token rotation: old deleted, new stored."""
        user_id = uuid.uuid4()
        mock_cache.get.return_value = str(user_id)

        use_case = RefreshTokenUseCase(
            mock_jwt_service, mock_cache,
            refresh_token_ttl_seconds=REFRESH_TTL,
        )
        await use_case(RefreshDTO(refresh_token="old-token"))

        
        mock_cache.delete.assert_awaited_once_with("refresh:old-token")
        
        set_call = mock_cache.set.call_args
        assert set_call.kwargs["key"] == "refresh:refresh-token-456"
