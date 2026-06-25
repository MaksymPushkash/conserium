import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.auth.jwt_service import JWTService
from src.documents.note_dependencies import get_note_service
from src.documents.schemas import NoteResponse
from src.documents.status import DocumentStatus
from src.knowledge_gaps.schemas import KnowledgeGap, KnowledgeGapArea, KnowledgeGapListResult
from src.knowledge_gaps.service import (
    get_knowledge_gap_service,
    to_knowledge_gap_list_response,
    to_knowledge_gap_response,
    to_note_response,
)
from src.main import create_app
from src.models.user import UserModel
from src.postgres import get_db_read_session
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


class _KnowledgeGapService:
    def __init__(self, result: KnowledgeGapListResult) -> None:
        self._result = result
        self.received: dict[str, object] = {}

    async def list(self, session: object, **kwargs: object):
        self.received = kwargs
        return to_knowledge_gap_list_response(self._result)


class _KnowledgeGapDetailService:
    def __init__(self, result: KnowledgeGap) -> None:
        self._result = result
        self.received: dict[str, object] = {}

    async def get(self, session: object, **kwargs: object):
        self.received = kwargs
        return to_knowledge_gap_response(self._result)


class _KnowledgeGapNoteService:
    def __init__(self, result: NoteResponse) -> None:
        self._result = result
        self.received: dict[str, object] = {}

    async def create_note(self, **kwargs: object):
        self.received = kwargs
        return to_note_response(self._result)


async def _session_override():
    yield object()


def _dependency_override(dependency: object):
    def override() -> object:
        return dependency

    return override


def test_list_knowledge_gaps_route_forwards_collection_scope() -> None:
    user = _make_user()
    collection_id = uuid.uuid4()
    service = _KnowledgeGapService(KnowledgeGapListResult(items=[_gap(collection_id=collection_id)], total=1))
    client = _client(user, {})
    client.app.dependency_overrides[get_knowledge_gap_service] = _dependency_override(service)
    client.app.dependency_overrides[get_db_read_session] = _session_override

    try:
        response = client.get(
            f"/api/v1/knowledge-gaps?collection_id={collection_id}&limit=5",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["topic"] == "Python"
    assert response.json()["items"][0]["missing_source_types"] == ["reference"]
    assert service.received == {"user_id": user.id, "collection_id": collection_id, "limit": 5}


def test_get_knowledge_gap_detail_route_forwards_topic_scope() -> None:
    user = _make_user()
    collection_id = uuid.uuid4()
    service = _KnowledgeGapDetailService(_gap(collection_id=collection_id))
    client = _client(user, {})
    client.app.dependency_overrides[get_knowledge_gap_service] = _dependency_override(service)
    client.app.dependency_overrides[get_db_read_session] = _session_override

    try:
        response = client.get(
            f"/api/v1/knowledge-gaps/Python?collection_id={collection_id}",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["areas"][0]["why_detected"] == "No saved source matched Testing."
    assert service.received == {"user_id": user.id, "topic": "Python", "collection_id": collection_id}


def test_create_knowledge_gap_note_route_creates_note_from_gap_payload() -> None:
    user = _make_user()
    collection_id = uuid.uuid4()
    note_id = uuid.uuid4()
    service = _KnowledgeGapNoteService(
        NoteResponse(
            id=note_id,
            collection_id=collection_id,
            title="Fill gap: Python - Testing",
            content="# Fill gap",
            status=DocumentStatus.READY,
            word_count=3,
            language="en",
            created_at=datetime(2026, 5, 24, tzinfo=UTC),
            updated_at=None,
        )
    )
    note_service = object()
    client = _client(user, {})
    client.app.dependency_overrides[get_knowledge_gap_service] = _dependency_override(service)
    client.app.dependency_overrides[get_note_service] = _dependency_override(note_service)

    try:
        response = client.post(
            "/api/v1/knowledge-gaps/python--testing/note",
            json={"topic": "Python", "area_name": "Testing", "collection_id": str(collection_id)},
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 201
    assert response.json()["id"] == str(note_id)
    assert service.received == {
        "note_service": note_service,
        "user_id": user.id,
        "gap_id": "python--testing",
        "topic": "Python",
        "area_name": "Testing",
        "collection_id": collection_id,
    }


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
    return TestClient(app, raise_server_exceptions=False)


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


def _gap(collection_id: uuid.UUID | None = None) -> KnowledgeGap:
    return KnowledgeGap(
        id="python--summary",
        topic="Python",
        collection_id=collection_id,
        covered_count=1,
        missing_count=1,
        coverage_ratio=0.5,
        why_detected="1 rubric area is missing.",
        missing_source_types=["reference"],
        severity="medium",
        rationale="Testing coverage is weak.",
        suggested_actions=["Add a testing reference."],
        areas=[
            KnowledgeGapArea(
                id="python--testing",
                name="Testing",
                covered=False,
                evidence_count=0,
                evidence_titles=[],
                why_detected="No saved source matched Testing.",
                missing_source_types=["reference"],
                severity="medium",
                rationale="Testing is missing.",
                suggested_actions=["Create a testing note."],
            )
        ],
    )
