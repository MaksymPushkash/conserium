import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth.jwt_service import JWTServiceProtocol
from src.documents.exports import NotionMarkdownExporter
from src.integrations.schemas import NotionPageResponse
from src.integrations.service import NotionWorkspaceService
from src.kit.exceptions import IntegrationConfigurationException, IntegrationRequestException
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


class _MissingParentNotionExportService:
    async def __call__(self, dto: object) -> object:
        raise IntegrationConfigurationException("set a default Notion parent page before exporting")


class _RejectedNotionPageSearchService:
    async def search_pages(self, *, user_id: uuid.UUID, query: str | None, limit: int) -> list[NotionPageResponse]:
        raise IntegrationRequestException("notion rejected the page search request")


def test_notion_export_without_parent_page_returns_422() -> None:
    user = _make_user()
    app = _make_app(
        user,
        {
            NotionMarkdownExporter: _MissingParentNotionExportService(),
        },
    )
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.post(
            "/api/v1/exports/notion",
            headers={"Authorization": "Bearer access-token"},
            json={"title": "Draft", "markdown": "# Draft"},
        )
    finally:
        client.close()

    assert response.status_code == 422
    assert response.json()["detail"] == "set a default Notion parent page before exporting"


def test_notion_page_search_rejected_returns_502() -> None:
    user = _make_user()
    app = _make_app(
        user,
        {
            NotionWorkspaceService: _RejectedNotionPageSearchService(),
        },
    )
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get(
            "/api/v1/integrations/notion/pages",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 502
    assert response.json()["detail"] == "notion rejected the page search request"


def _make_app(user: UserModel, dependencies: Mapping[type[object], object]) -> FastAPI:
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTServiceProtocol: jwt_service,
            UserRepository: _FakeRepositorySession(user),
            **dependencies,
        }
    )._dependencies)
    return app


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
