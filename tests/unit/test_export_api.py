import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.auth.jwt_service import JWTServiceProtocol
from src.main import create_app
from src.models.user import UserModel
from src.users.repository import UserRepository
from tests.dependency_overrides import apply_dependency_overrides


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


class _FakeDependencyContainer:
    def __init__(self, dependencies: Mapping[type[object], object]) -> None:
        self._dependencies = dependencies

    def __call__(self, context: object, scope: object) -> _FakeScopeContext:
        return _FakeScopeContext(self._dependencies)


class _FakeUserRepository:
    def __init__(self, user: UserModel) -> None:
        self._user = user

    async def get_by_id(self, user_id: uuid.UUID) -> UserModel | None:
        return self._user


class _FakeRepositorySession:
    def __init__(self, user: UserModel) -> None:
        self.user_repo = _FakeUserRepository(user)

    async def __aenter__(self) -> "_FakeRepositorySession":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def test_markdown_export_route_returns_attachment() -> None:
    user = _make_user()
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer({JWTServiceProtocol: jwt_service, UserRepository: _FakeRepositorySession(user)})._dependencies)
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.post(
            "/api/v1/exports/markdown",
            headers={"Authorization": "Bearer access-token"},
            json={"title": "Draft", "markdown": "# Draft\n\nBody", "format": "markdown"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="Draft.md"'
    assert response.text == "# Draft\n\nBody"


def test_pdf_export_route_returns_pdf_attachment() -> None:
    user = _make_user()
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer({JWTServiceProtocol: jwt_service, UserRepository: _FakeRepositorySession(user)})._dependencies)
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.post(
            "/api/v1/exports/markdown",
            headers={"Authorization": "Bearer access-token"},
            json={"title": "Draft", "markdown": "# Draft\n\nBody", "format": "pdf"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="Draft.pdf"'
    assert response.content.startswith(b"%PDF-1.4")


def _make_user() -> UserModel:
    return UserModel(
        id=uuid.uuid4(),
        email="user@example.com",
        password="$2b$12$hashedpassword",
        display_name="Test User",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=None,
    )
