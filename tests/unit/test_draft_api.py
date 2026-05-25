import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.draft_dtos import (
    DraftDetailDTO,
    DraftListDTO,
    DraftListItemDTO,
    DraftOutlineDTO,
    DraftResultDTO,
    DraftTemplateDTO,
    DraftVersionDTO,
)
from src.application.dtos.query_dtos import QuerySourceDTO
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.drafts import (
    DeleteDraftUseCase,
    GenerateDraftOutlineUseCase,
    GenerateDraftUseCase,
    GetDraftUseCase,
    ListDraftsUseCase,
    ListDraftTemplatesUseCase,
    ListDraftVersionsUseCase,
    RestoreDraftVersionUseCase,
)
from src.domain.entities.user_entity import UserEntity
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


class _ReturningDraftUseCase:
    def __init__(self, result: DraftResultDTO) -> None:
        self._result = result
        self.received = None

    async def __call__(self, dto):
        self.received = dto
        return self._result


class _ReturningTemplatesUseCase:
    async def __call__(self) -> list[DraftTemplateDTO]:
        return [
            DraftTemplateDTO(
                id="brief",
                name="Brief",
                description="Concise cited summary.",
                prompt="Write a concise brief.",
                outline=["Context", "Key points"],
            )
        ]


class _ReturningOutlineUseCase:
    def __init__(self) -> None:
        self.received = None

    async def __call__(self, dto):
        self.received = dto
        return DraftOutlineDTO(
            prompt=dto.prompt,
            template_id=dto.template_id,
            scope_type=dto.scope_type,
            title="Brief: Python generators",
            sections=["Context", "Key points"],
        )


class _ReturningDraftListUseCase:
    def __init__(self, result: DraftListDTO) -> None:
        self._result = result
        self.received: dict[str, object] = {}

    async def __call__(self, **kwargs: object) -> DraftListDTO:
        self.received = kwargs
        return self._result


class _ReturningDraftDetailUseCase:
    def __init__(self, result: DraftDetailDTO) -> None:
        self._result = result
        self.received: dict[str, object] = {}

    async def __call__(self, **kwargs: object) -> DraftDetailDTO:
        self.received = kwargs
        return self._result


class _ReturningDraftVersionsUseCase:
    def __init__(self, result: list[DraftVersionDTO]) -> None:
        self._result = result
        self.received: dict[str, object] = {}

    async def __call__(self, **kwargs: object) -> list[DraftVersionDTO]:
        self.received = kwargs
        return self._result


class _DeletingDraftUseCase:
    def __init__(self) -> None:
        self.received: dict[str, object] = {}

    async def __call__(self, **kwargs: object) -> None:
        self.received = kwargs


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


def test_generate_draft_route_returns_markdown_and_sources() -> None:
    user = _make_user()
    document_id = uuid.uuid4()
    source = QuerySourceDTO(
        chunk_id=uuid.uuid4(),
        document_id=document_id,
        document_title="Python Notes",
        content="Generators yield values lazily.",
        page_number=None,
        chunk_index=0,
        score=0.9,
        used_in_answer=True,
    )
    use_case = _ReturningDraftUseCase(
        DraftResultDTO(
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
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            GenerateDraftUseCase: use_case,
        }
    )
    client = TestClient(app, raise_server_exceptions=False)

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
    assert use_case.received.prompt == "Write about Python generators"
    assert use_case.received.topic == "Python"


def test_list_draft_templates_route_returns_structured_templates() -> None:
    user = _make_user()
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            ListDraftTemplatesUseCase: _ReturningTemplatesUseCase(),
        }
    )
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/drafts/templates", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "brief"
    assert response.json()["items"][0]["outline"] == ["Context", "Key points"]


def test_generate_draft_outline_route_forwards_scope() -> None:
    user = _make_user()
    use_case = _ReturningOutlineUseCase()
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            GenerateDraftOutlineUseCase: use_case,
        }
    )
    client = TestClient(app, raise_server_exceptions=False)

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
    assert use_case.received.scope_type == "collection"


def test_list_drafts_route_returns_recent_drafts() -> None:
    user = _make_user()
    collection_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    use_case = _ReturningDraftListUseCase(
        DraftListDTO(
            items=[
                DraftListItemDTO(
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
    client = _client(user, {ListDraftsUseCase: use_case})

    try:
        response = client.get(f"/api/v1/drafts?collection_id={collection_id}&limit=5", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == str(draft_id)
    assert use_case.received == {"user_id": user.id, "collection_id": collection_id, "limit": 5, "offset": 0}


def test_get_draft_and_restore_version_routes_enforce_user_context() -> None:
    user = _make_user()
    draft_id = uuid.uuid4()
    version_id = uuid.uuid4()
    detail = _draft_detail(draft_id=draft_id, version_id=version_id)
    get_use_case = _ReturningDraftDetailUseCase(detail)
    restore_use_case = _ReturningDraftDetailUseCase(detail)
    versions_use_case = _ReturningDraftVersionsUseCase([_draft_version(draft_id=draft_id, version_id=version_id)])
    client = _client(
        user,
        {
            GetDraftUseCase: get_use_case,
            RestoreDraftVersionUseCase: restore_use_case,
            ListDraftVersionsUseCase: versions_use_case,
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
    assert get_use_case.received == {"user_id": user.id, "draft_id": draft_id}
    assert versions_use_case.received == {"user_id": user.id, "draft_id": draft_id}
    assert restore_use_case.received == {"user_id": user.id, "draft_id": draft_id, "version_id": version_id}


def test_delete_draft_route_forwards_user_context() -> None:
    user = _make_user()
    draft_id = uuid.uuid4()
    use_case = _DeletingDraftUseCase()
    client = _client(user, {DeleteDraftUseCase: use_case})

    try:
        response = client.delete(f"/api/v1/drafts/{draft_id}", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 204
    assert use_case.received == {"user_id": user.id, "draft_id": draft_id}


def _client(user: UserEntity, dependencies: Mapping[type[object], object]) -> TestClient:
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
    return TestClient(app, raise_server_exceptions=False)


def _draft_detail(*, draft_id: uuid.UUID, version_id: uuid.UUID) -> DraftDetailDTO:
    return DraftDetailDTO(
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


def _draft_version(*, draft_id: uuid.UUID, version_id: uuid.UUID) -> DraftVersionDTO:
    return DraftVersionDTO(
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
