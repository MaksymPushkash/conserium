import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.auth.jwt_service import JWTService
from src.kit.exceptions import ResourceNotFoundException
from src.main import create_app
from src.models.user import UserModel
from src.postgres import get_db_read_session, get_db_session
from src.users.repository import UserRepository
from src.workspaces.endpoints import get_workspace_service
from src.workspaces.schemas import (
    WorkspaceMemberRecord,
    WorkspaceRecord,
)
from src.workspaces.service import (
    to_workspace_member_response,
    to_workspace_response,
)
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
        return self._user if self._user.id == user_id else None


class _FakeRepositorySession:
    def __init__(self, user: UserModel) -> None:
        self.user_repo = _FakeUserRepository(user)

    async def __aenter__(self) -> "_FakeRepositorySession":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _TransferWorkspaceOwnership:
    def __init__(self, workspace: WorkspaceRecord) -> None:
        self.workspace = workspace
        self.received: object | None = None

    async def transfer_ownership(self, session: object, **kwargs: object):
        self.received = kwargs
        return to_workspace_response(self.workspace)


class _InviteWorkspaceMember:
    def __init__(self, member: WorkspaceMemberRecord | None = None, exc: Exception | None = None) -> None:
        self.member = member
        self.exc = exc
        self.received: object | None = None

    async def invite_member(self, session: object, **kwargs: object):
        self.received = kwargs
        if self.exc is not None:
            raise self.exc
        assert self.member is not None
        return to_workspace_member_response(self.member)


class _UpdateWorkspace:
    def __init__(self, workspace: WorkspaceRecord) -> None:
        self.workspace = workspace
        self.received: object | None = None

    async def update(self, session: object, **kwargs: object):
        self.received = kwargs
        return to_workspace_response(self.workspace)


class _DeleteWorkspace:
    def __init__(self) -> None:
        self.received: object | None = None

    async def delete(self, session: object, **kwargs: object) -> None:
        self.received = kwargs


async def _session_override():
    yield object()


def test_workspace_invite_route_forwards_owner_payload() -> None:
    user = _make_user()
    workspace_id = uuid.uuid4()
    member = WorkspaceMemberRecord(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        user_id=None,
        email="teammate@example.com",
        role="editor",
        invite_status="pending",
        invited_by_user_id=user.id,
        created_at=datetime.now(UTC),
        updated_at=None,
    )
    handler = _InviteWorkspaceMember(member)
    client = _client(user, handler)

    try:
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/members",
            headers={"Authorization": "Bearer access-token"},
            json={"email": "teammate@example.com", "role": "editor"},
        )
    finally:
        client.close()

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "teammate@example.com"
    assert payload["role"] == "editor"
    assert payload["invite_status"] == "pending"
    assert handler.received is not None
    assert handler.received["workspace_id"] == workspace_id
    assert handler.received["actor_user_id"] == user.id


def test_workspace_transfer_ownership_route_forwards_member_payload() -> None:
    user = _make_user()
    workspace_id = uuid.uuid4()
    member_id = uuid.uuid4()
    workspace = WorkspaceRecord(
        id=workspace_id,
        user_id=uuid.uuid4(),
        name="Team",
        description=None,
        access_role="owner",
        created_at=datetime.now(UTC),
        updated_at=None,
    )
    handler = _TransferWorkspaceOwnership(workspace)
    client = _client(user, handler)

    try:
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/transfer-ownership",
            headers={"Authorization": "Bearer access-token"},
            json={"member_id": str(member_id)},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["id"] == str(workspace_id)
    assert handler.received is not None
    assert handler.received["workspace_id"] == workspace_id
    assert handler.received["actor_user_id"] == user.id
    assert handler.received["member_id"] == member_id


def test_workspace_update_route_forwards_owner_payload() -> None:
    user = _make_user()
    workspace_id = uuid.uuid4()
    workspace = WorkspaceRecord(
        id=workspace_id,
        user_id=user.id,
        name="Updated team",
        description="Updated description",
        access_role="owner",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    handler = _UpdateWorkspace(workspace)
    client = _client(user, handler)

    try:
        response = client.patch(
            f"/api/v1/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer access-token"},
            json={"name": "Updated team", "description": "Updated description"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["name"] == "Updated team"
    assert handler.received is not None
    assert handler.received["workspace_id"] == workspace_id
    assert handler.received["actor_user_id"] == user.id


def test_workspace_delete_route_forwards_owner_payload() -> None:
    user = _make_user()
    workspace_id = uuid.uuid4()
    handler = _DeleteWorkspace()
    client = _client(user, handler)

    try:
        response = client.delete(
            f"/api/v1/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 204
    assert handler.received is not None
    assert handler.received["workspace_id"] == workspace_id
    assert handler.received["actor_user_id"] == user.id


def test_workspace_invite_route_rejects_owner_transfer_role() -> None:
    user = _make_user()
    handler = _InviteWorkspaceMember()
    client = _client(user, handler)

    try:
        response = client.post(
            f"/api/v1/workspaces/{uuid.uuid4()}/members",
            headers={"Authorization": "Bearer access-token"},
            json={"email": "teammate@example.com", "role": "owner"},
        )
    finally:
        client.close()

    assert response.status_code == 422
    assert handler.received is None


def test_workspace_invite_route_hides_workspace_when_service_denies_role() -> None:
    user = _make_user()
    handler = _InviteWorkspaceMember(exc=ResourceNotFoundException("workspace not found"))
    client = _client(user, handler)

    try:
        response = client.post(
            f"/api/v1/workspaces/{uuid.uuid4()}/members",
            headers={"Authorization": "Bearer access-token"},
            json={"email": "teammate@example.com", "role": "viewer"},
        )
    finally:
        client.close()

    assert response.status_code == 404


def _client(user: UserModel, service: object) -> TestClient:
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer({JWTService: jwt_service, UserRepository: _FakeRepositorySession(user)})._dependencies)
    app.dependency_overrides[get_workspace_service] = _dependency_override(service)
    app.dependency_overrides[get_db_session] = _session_override
    app.dependency_overrides[get_db_read_session] = _session_override
    return TestClient(app, raise_server_exceptions=False)


def _dependency_override(handler: object):
    def override() -> object:
        return handler

    return override


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
