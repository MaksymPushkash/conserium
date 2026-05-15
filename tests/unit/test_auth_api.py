import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from src.application.dtos.auth_dtos import TokenResponseDTO
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.auth.complete_oauth_login_use_case import CompleteOAuthLoginUseCase
from src.application.use_cases.auth.login_use_case import LoginUserUseCase
from src.application.use_cases.auth.refresh_token_use_case import RefreshTokenUseCase
from src.application.use_cases.auth.register_use_case import RegisterUserUseCase
from src.domain.entities.user_entity import UserEntity
from src.domain.exceptions import (
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    InvalidTokenException,
    OAuthAuthenticationException,
)
from src.domain.value_objects.email import Email
from src.infrastructure.auth.oauth_clients import GoogleOAuthClient
from src.main import _cors_origins, create_app


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


class _SuccessfulOAuthUseCase:
    async def __call__(self, dto: object, provider: object) -> TokenResponseDTO:
        return TokenResponseDTO(access_token="oauth-access-token", refresh_token="oauth-refresh-token")


class _FailingOAuthUseCase:
    async def __call__(self, dto: object, provider: object) -> TokenResponseDTO:
        raise OAuthAuthenticationException("no_email", "oauth provider did not return an email")


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


def test_debug_cors_includes_local_frontend_origins(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("src.main.settings.FRONTEND_URL", "https://app.example.com")
    monkeypatch.setattr("src.main.settings.DEBUG", True)

    assert _cors_origins() == [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "https://app.example.com",
    ]


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


def test_register_route_sets_refresh_cookie_without_json_refresh_token() -> None:
    client = _make_client({RegisterUserUseCase: _SuccessfulUseCase()})

    try:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "user@example.com", "password": "securepass123"},
        )
    finally:
        client.close()

    assert response.status_code == 201
    assert response.json() == {
        "access_token": "api-access-token",
        "token_type": "bearer",
    }
    assert "oauth_refresh_token=api-refresh-token" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_login_route_sets_refresh_cookie_without_json_refresh_token() -> None:
    client = _make_client({LoginUserUseCase: _SuccessfulUseCase()})

    try:
        response = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "securepass123"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "api-access-token",
        "token_type": "bearer",
    }
    assert "oauth_refresh_token=api-refresh-token" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_refresh_route_returns_token_response_from_injected_use_case() -> None:
    client = _make_client({RefreshTokenUseCase: _SuccessfulUseCase()})

    try:
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": "valid-refresh-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "api-access-token",
        "token_type": "bearer",
    }
    assert "oauth_refresh_token=api-refresh-token" in response.headers["set-cookie"]


def test_refresh_route_accepts_refresh_token_cookie() -> None:
    use_case = _SuccessfulUseCase()
    client = _make_client({RefreshTokenUseCase: use_case})

    try:
        response = client.post(
            "/api/v1/auth/refresh",
            cookies={"oauth_refresh_token": "cookie-refresh-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["access_token"] == "api-access-token"


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


def test_get_me_returns_401_without_authorization_header() -> None:
    user_id = uuid.uuid4()
    client = _make_client(
        {
            IJWTService: _make_jwt_service(user_id),
            IUnitOfWork: _FakeUnitOfWork(_make_user()),
        }
    )

    try:
        response = client.get("/api/v1/users/me")
    finally:
        client.close()

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_google_start_uses_forwarded_origin_and_sets_state_cookie() -> None:
    client = _make_client(
        {
            GoogleOAuthClient: GoogleOAuthClient(client_id="google-client", client_secret="google-secret"),
        }
    )

    try:
        response = client.get(
            "/api/v1/auth/google",
            headers={"x-forwarded-proto": "https", "x-forwarded-host": "api.example.com"},
            follow_redirects=False,
        )
    finally:
        client.close()

    assert response.status_code == 307
    assert "https://accounts.google.com/o/oauth2/v2/auth" in response.headers["location"]
    assert "redirect_uri=https%3A%2F%2Fapi.example.com%2Fapi%2Fv1%2Fauth%2Fgoogle%2Fcallback" in response.headers[
        "location"
    ]
    assert "oauth_state=" in response.headers["set-cookie"]


def test_google_callback_redirects_access_token_in_fragment_and_refresh_token_cookie() -> None:
    client = _make_client(
        {
            GoogleOAuthClient: GoogleOAuthClient(client_id="google-client", client_secret="google-secret"),
            CompleteOAuthLoginUseCase: _SuccessfulOAuthUseCase(),
        }
    )

    try:
        response = client.get(
            "/api/v1/auth/google/callback?code=oauth-code&state=state-token",
            cookies={"oauth_state": "state-token"},
            follow_redirects=False,
        )
    finally:
        client.close()

    assert response.status_code == 302
    location = response.headers["location"]
    assert "/auth/callback#" in location
    assert "?access_token=" not in location
    assert "access_token=oauth-access-token" in location
    assert "refresh_token=" not in location
    set_cookie = response.headers["set-cookie"]
    assert "oauth_refresh_token=oauth-refresh-token" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "oauth_state=" in set_cookie


def test_google_callback_can_include_refresh_token_in_fragment_for_legacy_frontend(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.presentation.oauth_redirects.settings.OAUTH_INCLUDE_REFRESH_TOKEN_IN_FRAGMENT",
        True,
    )
    client = _make_client(
        {
            GoogleOAuthClient: GoogleOAuthClient(client_id="google-client", client_secret="google-secret"),
            CompleteOAuthLoginUseCase: _SuccessfulOAuthUseCase(),
        }
    )

    try:
        response = client.get(
            "/api/v1/auth/google/callback?code=oauth-code&state=state-token",
            cookies={"oauth_state": "state-token"},
            follow_redirects=False,
        )
    finally:
        client.close()

    assert response.status_code == 302
    assert "refresh_token=oauth-refresh-token" in response.headers["location"]


def test_google_callback_redirects_invalid_state_error() -> None:
    client = _make_client(
        {
            GoogleOAuthClient: GoogleOAuthClient(client_id="google-client", client_secret="google-secret"),
            CompleteOAuthLoginUseCase: _SuccessfulOAuthUseCase(),
        }
    )

    try:
        response = client.get(
            "/api/v1/auth/google/callback?code=oauth-code&state=state-token",
            cookies={"oauth_state": "different-state"},
            follow_redirects=False,
        )
    finally:
        client.close()

    assert response.status_code == 302
    assert response.headers["location"].endswith("/auth?error=invalid_state")


def test_google_callback_redirects_oauth_error_code() -> None:
    client = _make_client(
        {
            GoogleOAuthClient: GoogleOAuthClient(client_id="google-client", client_secret="google-secret"),
            CompleteOAuthLoginUseCase: _FailingOAuthUseCase(),
        }
    )

    try:
        response = client.get(
            "/api/v1/auth/google/callback?code=oauth-code&state=state-token",
            cookies={"oauth_state": "state-token"},
            follow_redirects=False,
        )
    finally:
        client.close()

    assert response.status_code == 302
    assert response.headers["location"].endswith("/auth?error=no_email")
