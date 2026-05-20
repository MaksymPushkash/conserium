import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.collection_share_dtos import (
    CollectionShareDTO,
    PublicCollectionDocumentDTO,
    PublicCollectionDTO,
)
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.collection_shares import CreateCollectionShareUseCase, GetPublicCollectionUseCase
from src.domain.entities.user_entity import UserEntity
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType
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


class _ReturningCreateShareUseCase:
    def __init__(self, share: CollectionShareDTO) -> None:
        self._share = share
        self.received: tuple[uuid.UUID, uuid.UUID] | None = None

    async def __call__(self, *, user_id: uuid.UUID, collection_id: uuid.UUID) -> CollectionShareDTO:
        self.received = (user_id, collection_id)
        return self._share


class _ReturningPublicCollectionUseCase:
    def __init__(self, collection: PublicCollectionDTO) -> None:
        self._collection = collection
        self.received: str | None = None

    async def __call__(self, *, slug: str) -> PublicCollectionDTO:
        self.received = slug
        return self._collection


def test_create_collection_share_route_returns_slug() -> None:
    user = _make_user()
    collection_id = uuid.uuid4()
    share = CollectionShareDTO(
        id=uuid.uuid4(),
        collection_id=collection_id,
        user_id=user.id,
        slug="public-slug",
        include_summaries=True,
        include_notes=False,
        revoked_at=None,
        created_at=datetime.now(UTC),
        updated_at=None,
    )
    use_case = _ReturningCreateShareUseCase(share)
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            CreateCollectionShareUseCase: use_case,
        }
    )
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.post(
            f"/api/v1/collections/{collection_id}/share",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 201
    assert response.json()["slug"] == "public-slug"
    assert "user_id" not in response.json()
    assert use_case.received == (user.id, collection_id)


def test_public_collection_route_returns_no_private_user_fields() -> None:
    collection = PublicCollectionDTO(
        id=uuid.uuid4(),
        name="Python",
        description="Python material",
        color="#ffffff",
        documents=[
            PublicCollectionDocumentDTO(
                id=uuid.uuid4(),
                title="Async Python",
                type=DocumentType.TEXT,
                status=DocumentStatus.READY,
                source_url="https://example.com/python",
                summary="Short summary.",
                word_count=120,
                language="en",
                tags=["python"],
                created_at=datetime.now(UTC),
                updated_at=None,
            )
        ],
        created_at=datetime.now(UTC),
        updated_at=None,
    )
    use_case = _ReturningPublicCollectionUseCase(collection)
    app = create_app()
    app.state.dishka_container = _FakeRootContainer({GetPublicCollectionUseCase: use_case})
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/public/collections/public-slug")
    finally:
        client.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Python"
    assert payload["documents"][0]["summary"] == "Short summary."
    assert "user_id" not in payload
    assert "raw_content" not in payload["documents"][0]
    assert use_case.received == "public-slug"


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
