import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.auth.jwt_service import JWTService
from src.drafts.dependencies import get_draft_service
from src.drafts.operations import (
    DraftGenerator,
    delete_draft,
    generate_draft_outline,
    get_draft,
    list_draft_templates,
    list_draft_versions,
    list_drafts,
    restore_draft_version,
)
from src.drafts.schemas import (
    DraftDetail,
    DraftListItem,
    DraftListResult,
    DraftOutline,
    DraftResult,
    DraftTemplate,
    DraftVersion,
)
from src.drafts.service import (
    build_draft_generation_input,
    to_draft_detail_response,
    to_draft_list_response,
    to_draft_outline_response,
    to_draft_response,
    to_draft_template_list_response,
    to_draft_version_list_response,
)
from src.main import create_app
from src.models.user import UserModel
from src.query.schemas import QuerySource
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


class _ReturningDraftService:
    def __init__(self, result: DraftResult) -> None:
        self._result = result
        self.received = None

    async def __call__(self, dto):
        self.received = dto
        return self._result


class _ReturningTemplatesService:
    async def __call__(self) -> list[DraftTemplate]:
        return [
            DraftTemplate(
                id="brief",
                name="Brief",
                description="Concise cited summary.",
                prompt="Write a concise brief.",
                outline=["Context", "Key points"],
            )
        ]


class _ReturningOutlineService:
    def __init__(self) -> None:
        self.received = None

    async def __call__(self, dto):
        self.received = dto
        return DraftOutline(
            prompt=dto.prompt,
            template_id=dto.template_id,
            scope_type=dto.scope_type,
            title="Brief: Python generators",
            sections=["Context", "Key points"],
        )


class _ReturningDraftListService:
    def __init__(self, result: DraftListResult) -> None:
        self._result = result
        self.received: dict[str, object] = {}

    async def __call__(self, **kwargs: object) -> DraftListResult:
        self.received = kwargs
        return self._result


class _ReturningDraftDetailService:
    def __init__(self, result: DraftDetail) -> None:
        self._result = result
        self.received: dict[str, object] = {}

    async def __call__(self, **kwargs: object) -> DraftDetail:
        self.received = kwargs
        return self._result


class _ReturningDraftVersionsService:
    def __init__(self, result: list[DraftVersion]) -> None:
        self._result = result
        self.received: dict[str, object] = {}

    async def __call__(self, **kwargs: object) -> list[DraftVersion]:
        self.received = kwargs
        return self._result


class _DeletingDraftService:
    def __init__(self) -> None:
        self.received: dict[str, object] = {}

    async def __call__(self, **kwargs: object) -> None:
        self.received = kwargs


class _DraftServiceFromServices:
    def __init__(self, dependencies: Mapping[type[object], object]) -> None:
        self._dependencies = dependencies

    async def list(self, *, user_id: uuid.UUID, collection_id: uuid.UUID | None, limit: int, offset: int):
        handler = self._dependencies[list_drafts]
        return to_draft_list_response(
            await handler(user_id=user_id, collection_id=collection_id, limit=limit, offset=offset)
        )

    async def list_templates(self):
        handler = self._dependencies[list_draft_templates]
        return to_draft_template_list_response(await handler())

    async def generate_outline(self, *, user_id: uuid.UUID, body: object):
        handler = self._dependencies[generate_draft_outline]
        return to_draft_outline_response(await handler(build_draft_generation_input(body, user_id)))

    async def generate(self, *, user_id: uuid.UUID, body: object):
        handler = self._dependencies[DraftGenerator]
        return to_draft_response(await handler(build_draft_generation_input(body, user_id)))

    async def get(self, *, user_id: uuid.UUID, draft_id: uuid.UUID):
        handler = self._dependencies[get_draft]
        return to_draft_detail_response(await handler(user_id=user_id, draft_id=draft_id))

    async def list_versions(self, *, user_id: uuid.UUID, draft_id: uuid.UUID):
        handler = self._dependencies[list_draft_versions]
        return to_draft_version_list_response(await handler(user_id=user_id, draft_id=draft_id))

    async def restore_version(self, *, user_id: uuid.UUID, draft_id: uuid.UUID, version_id: uuid.UUID):
        handler = self._dependencies[restore_draft_version]
        return to_draft_detail_response(await handler(user_id=user_id, draft_id=draft_id, version_id=version_id))

    async def delete(self, *, user_id: uuid.UUID, draft_id: uuid.UUID) -> None:
        handler = self._dependencies[delete_draft]
        await handler(user_id=user_id, draft_id=draft_id)


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


def test_generate_draft_route_returns_markdown_and_sources() -> None:
    user = _make_user()
    document_id = uuid.uuid4()
    source = QuerySource(
        chunk_id=uuid.uuid4(),
        document_id=document_id,
        document_title="Python Notes",
        content="Generators yield values lazily.",
        page_number=None,
        chunk_index=0,
        score=0.9,
        used_in_answer=True,
    )
    handler = _ReturningDraftService(
        DraftResult(
            draft_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            version_number=1,
            prompt="Write about Python generators",
            template_id="brief",
            scope_type="topic",
            markdown="# Python generators\n\nGenerators yield values lazily [1].",
            sources=[source],
            gaps=[],
        )
    )
    client = _client(user, {DraftGenerator: handler})

    try:
        response = client.post(
            "/api/v1/drafts/generate",
            headers={"Authorization": "Bearer access-token"},
            json={"prompt": "Write about Python generators", "template_id": "brief", "scope_type": "topic", "topic": "Python", "limit": 8},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["draft_id"]
    assert response.json()["version_id"]
    assert response.json()["version_number"] == 1
    assert response.json()["markdown"].startswith("# Python generators")
    assert response.json()["template_id"] == "brief"
    assert response.json()["scope_type"] == "topic"
    assert response.json()["sources"][0]["document_id"] == str(document_id)
    assert response.json()["gaps"] == []
    assert handler.received is not None
    assert handler.received.prompt == "Write about Python generators"
    assert handler.received.topic == "Python"


def test_list_draft_templates_route_returns_structured_templates() -> None:
    user = _make_user()
    client = _client(user, {list_draft_templates: _ReturningTemplatesService()})

    try:
        response = client.get("/api/v1/drafts/templates", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "brief"
    assert response.json()["items"][0]["outline"] == ["Context", "Key points"]


def test_generate_draft_outline_route_forwards_scope() -> None:
    user = _make_user()
    handler = _ReturningOutlineService()
    client = _client(user, {generate_draft_outline: handler})

    try:
        response = client.post(
            "/api/v1/drafts/outline",
            headers={"Authorization": "Bearer access-token"},
            json={"prompt": "Write about Python generators", "scope_type": "collection", "collection_id": str(uuid.uuid4())},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["sections"] == ["Context", "Key points"]
    assert handler.received is not None
    assert handler.received.scope_type == "collection"


def test_list_drafts_route_returns_recent_drafts() -> None:
    user = _make_user()
    collection_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    handler = _ReturningDraftListService(
        DraftListResult(
            items=[
                DraftListItem(
                    id=draft_id,
                    collection_id=collection_id,
                    title="Brief: Python",
                    prompt="Write about Python",
                    template_id="brief",
                    scope_type="collection",
                    topic="python",
                    knowledge_gap_id=None,
                    version_number=2,
                    created_at=datetime(2026, 5, 25, tzinfo=UTC),
                    updated_at=None,
                )
            ],
            total=1,
        )
    )
    client = _client(user, {list_drafts: handler})

    try:
        response = client.get(f"/api/v1/drafts?collection_id={collection_id}&limit=5", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == str(draft_id)
    assert handler.received == {"user_id": user.id, "collection_id": collection_id, "limit": 5, "offset": 0}


def test_get_draft_and_restore_version_routes_enforce_user_context() -> None:
    user = _make_user()
    draft_id = uuid.uuid4()
    version_id = uuid.uuid4()
    detail = _draft_detail(draft_id=draft_id, version_id=version_id)
    get_handler = _ReturningDraftDetailService(detail)
    restore_service = _ReturningDraftDetailService(detail)
    versions_service = _ReturningDraftVersionsService([_draft_version(draft_id=draft_id, version_id=version_id)])
    client = _client(
        user,
        {
            get_draft: get_handler,
            restore_draft_version: restore_service,
            list_draft_versions: versions_service,
        },
    )

    try:
        get_response = client.get(f"/api/v1/drafts/{draft_id}", headers={"Authorization": "Bearer access-token"})
        versions_response = client.get(f"/api/v1/drafts/{draft_id}/versions", headers={"Authorization": "Bearer access-token"})
        restore_response = client.post(f"/api/v1/drafts/{draft_id}/versions/{version_id}/restore", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert get_response.status_code == 200
    assert versions_response.status_code == 200
    assert restore_response.status_code == 200
    assert get_handler.received == {"user_id": user.id, "draft_id": draft_id}
    assert versions_service.received == {"user_id": user.id, "draft_id": draft_id}
    assert restore_service.received == {"user_id": user.id, "draft_id": draft_id, "version_id": version_id}


def test_delete_draft_route_forwards_user_context() -> None:
    user = _make_user()
    draft_id = uuid.uuid4()
    handler = _DeletingDraftService()
    client = _client(user, {delete_draft: handler})

    try:
        response = client.delete(f"/api/v1/drafts/{draft_id}", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 204
    assert handler.received == {"user_id": user.id, "draft_id": draft_id}


def _client(user: UserModel, dependencies: Mapping[type[object], object]) -> TestClient:
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTService: jwt_service,
            UserRepository: _FakeRepositorySession(user),
            **dependencies,
        }
    )._dependencies)
    app.dependency_overrides[get_draft_service] = lambda: _DraftServiceFromServices(dependencies)
    return TestClient(app, raise_server_exceptions=False)


def _draft_detail(*, draft_id: uuid.UUID, version_id: uuid.UUID) -> DraftDetail:
    return DraftDetail(
        id=draft_id,
        collection_id=None,
        current_version_id=version_id,
        title="Brief: Python",
        prompt="Write about Python",
        template_id="brief",
        scope_type="all",
        topic=None,
        knowledge_gap_id=None,
        scope_metadata={},
        markdown="# Python",
        sources=[],
        gaps=[],
        version_number=1,
        created_at=datetime(2026, 5, 25, tzinfo=UTC),
        updated_at=None,
    )


def _draft_version(*, draft_id: uuid.UUID, version_id: uuid.UUID) -> DraftVersion:
    return DraftVersion(
        id=version_id,
        draft_id=draft_id,
        version_number=1,
        title="Brief: Python",
        prompt="Write about Python",
        template_id="brief",
        scope_type="all",
        collection_id=None,
        topic=None,
        knowledge_gap_id=None,
        markdown="# Python",
        sources=[],
        gaps=[],
        created_at=datetime(2026, 5, 25, tzinfo=UTC),
    )
