import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.auth_dtos import TokenResponseDTO
from src.application.interfaces.jwt_service import IJWTService
from src.application.interfaces.unit_of_work import IUnitOfWork
from src.application.use_cases.auth.login_use_case import LoginUserUseCase
from src.application.use_cases.auth.refresh_token_use_case import RefreshTokenUseCase
from src.application.use_cases.auth.register_use_case import RegisterUserUseCase
from src.domain.entities.user_entity import UserEntity
from src.domain.exceptions import EmailAlreadyExistsException, InvalidCredentialsException, InvalidTokenException
from src.domain.value_objects.email import Email
from src.main import create_app


class _FakeRequestContainer:
    def __init__(self, dependencies: Mapping[type[object], object]) -> None:
        self._dependencies = dependencies

    async def get(self, type_hint: type[object], component: str = "") -> object:
        return self._dependencies[type_hint]


class _FakeScopeContext:
    def __init__(self, dependencies: Mapping[type[object], object]) -> None:
        self._request_container = _FakeRequestContainer(dependencies)

    async def __aenter__(self) -> _FakeRequestContainer:
        return self._request_container

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _FakeRootContainer:
    def __init__(self, dependencies: Mapping[type[object], object]) -> None:
        self._dependencies = dependencies

    def __call__(self, context: object, scope: object) -> _FakeScopeContext:
        return _FakeScopeContext(self._dependencies)


class _RaisingUseCase:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def __call__(self, dto: object) -> TokenResponseDTO:
        raise self._exc


class _SuccessfulUseCase:
    async def __call__(self, dto: object) -> TokenResponseDTO:
        return TokenResponseDTO(access_token="api-access-token", refresh_token="api-refresh-token")


class _FakeUserRepository:
    def __init__(self, user: UserEntity | None) -> None:
        self._user = user

    async def get_by_id(self, user_id: uuid.UUID) -> UserEntity | None:
        return self._user


class _FakeUnitOfWork:
    def __init__(self, user: UserEntity | None) -> None:
        self.user_repo = _FakeUserRepository(user)

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def _make_user(*, is_active: bool = True) -> UserEntity:
    return UserEntity(
        id=uuid.uuid4(),
        email=Email(value="user@example.com"),
        password="$2b$12$hashedpassword",
        display_name="Test User",
        is_active=is_active,
        created_at=datetime.now(UTC),
        updated_at=None,
    )


def _make_jwt_service(user_id: uuid.UUID) -> MagicMock:
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user_id
    return jwt_service


def _make_client(dependencies: Mapping[type[object], object]) -> TestClient:
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(dependencies)
    return TestClient(app, raise_server_exceptions=False)


def test_refresh_route_maps_invalid_token_exception() -> None:
    client = _make_client(
        {
            RefreshTokenUseCase: _RaisingUseCase(InvalidTokenException("refresh token invalid")),
        }
    )

    try:
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": "bad-refresh-token"})
    finally:
        client.close()

    assert response.status_code == 401
    assert response.json() == {"detail": "refresh token invalid"}


def test_login_route_maps_invalid_credentials_exception() -> None:
    client = _make_client(
        {
            LoginUserUseCase: _RaisingUseCase(InvalidCredentialsException("invalid email or password")),
        }
    )

    try:
        response = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "wrong"})
    finally:
        client.close()

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid email or password"}


def test_register_route_maps_duplicate_email_exception() -> None:
    client = _make_client(
        {
            RegisterUserUseCase: _RaisingUseCase(EmailAlreadyExistsException("user@example.com already registered")),
        }
    )

    try:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "user@example.com", "password": "securepass123"},
        )
    finally:
        client.close()

    assert response.status_code == 409
    assert response.json() == {"detail": "user@example.com already registered"}


def test_refresh_route_returns_token_response_from_injected_use_case() -> None:
    client = _make_client({RefreshTokenUseCase: _SuccessfulUseCase()})

    try:
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": "valid-refresh-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "api-access-token",
        "refresh_token": "api-refresh-token",
        "token_type": "bearer",
    }


def test_get_me_returns_401_for_deleted_user() -> None:
    user_id = uuid.uuid4()
    client = _make_client(
        {
            IJWTService: _make_jwt_service(user_id),
            IUnitOfWork: _FakeUnitOfWork(user=None),
        }
    )

    try:
        response = client.get("/api/v1/users/me", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 401
    assert response.json() == {"detail": "user not found"}


def test_get_me_returns_403_for_inactive_user() -> None:
    user_id = uuid.uuid4()
    client = _make_client(
        {
            IJWTService: _make_jwt_service(user_id),
            IUnitOfWork: _FakeUnitOfWork(user=_make_user(is_active=False)),
        }
    )

    try:
        response = client.get("/api/v1/users/me", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 403
    assert response.json() == {"detail": "user inactive"}
