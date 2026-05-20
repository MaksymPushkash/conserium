import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.dtos.external_connection_dtos import NotionPageDTO
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.export_markdown_to_notion_use_case import ExportMarkdownToNotionUseCase
from src.application.use_cases.integrations import SearchNotionPagesUseCase
from src.domain.entities.user_entity import UserEntity
from src.domain.exceptions import IntegrationConfigurationException, IntegrationRequestException
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


class _FakeUserRepository:
    def __init__(self, user: UserEntity) -> None:
        self._user = user

    async def get_by_id(self, user_id: uuid.UUID) -> UserEntity | None:
        return self._user


class _FakeUnitOfWork:
    def __init__(self, user: UserEntity) -> None:
        self.user_repo = _FakeUserRepository(user)

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _MissingParentNotionExportUseCase:
    async def __call__(self, dto: object) -> object:
        raise IntegrationConfigurationException("set a default Notion parent page before exporting")


class _RejectedNotionPageSearchUseCase:
    async def __call__(self, *, user_id: uuid.UUID, query: str | None, limit: int) -> list[NotionPageDTO]:
        raise IntegrationRequestException("notion rejected the page search request")


def test_notion_export_without_parent_page_returns_422() -> None:
    user = _make_user()
    app = _make_app(
        user,
        {
            ExportMarkdownToNotionUseCase: _MissingParentNotionExportUseCase(),
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
            SearchNotionPagesUseCase: _RejectedNotionPageSearchUseCase(),
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


def _make_app(user: UserEntity, dependencies: Mapping[type[object], object]) -> FastAPI:
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            **dependencies,
        }
    )
    return app


def _make_user() -> UserEntity:
    return UserEntity(
        id=uuid.uuid4(),
        email=Email(value="user@example.com"),
        password="$2b$12$hashedpassword",
        display_name="Test User",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=None,
    )
