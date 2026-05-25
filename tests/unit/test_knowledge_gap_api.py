import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.knowledge_gap_dtos import KnowledgeGapAreaDTO, KnowledgeGapDTO, KnowledgeGapListDTO
from src.application.dtos.note_dtos import NoteDTO
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.knowledge_gaps import (
    CreateKnowledgeGapNoteUseCase,
    GetKnowledgeGapsUseCase,
    ListKnowledgeGapsUseCase,
)
from src.domain.entities.user_entity import UserEntity
from src.domain.value_objects.document_status import DocumentStatus
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


class _ListGapsUseCase:
    def __init__(self, result: KnowledgeGapListDTO) -> None:
        self._result = result
        self.received: dict[str, object] = {}

    async def __call__(self, **kwargs: object) -> KnowledgeGapListDTO:
        self.received = kwargs
        return self._result


class _GetGapUseCase:
    def __init__(self, result: KnowledgeGapDTO) -> None:
        self._result = result
        self.received: dict[str, object] = {}

    async def __call__(self, **kwargs: object) -> KnowledgeGapDTO:
        self.received = kwargs
        return self._result


class _CreateGapNoteUseCase:
    def __init__(self, result: NoteDTO) -> None:
        self._result = result
        self.received: dict[str, object] = {}

    async def __call__(self, **kwargs: object) -> NoteDTO:
        self.received = kwargs
        return self._result


def test_list_knowledge_gaps_route_forwards_collection_scope() -> None:
    user = _make_user()
    collection_id = uuid.uuid4()
    use_case = _ListGapsUseCase(KnowledgeGapListDTO(items=[_gap(collection_id=collection_id)], total=1))
    client = _client(user, {ListKnowledgeGapsUseCase: use_case})

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
    assert use_case.received == {"user_id": user.id, "collection_id": collection_id, "limit": 5}


def test_get_knowledge_gap_detail_route_forwards_topic_scope() -> None:
    user = _make_user()
    collection_id = uuid.uuid4()
    use_case = _GetGapUseCase(_gap(collection_id=collection_id))
    client = _client(user, {GetKnowledgeGapsUseCase: use_case})

    try:
        response = client.get(
            f"/api/v1/knowledge-gaps/Python?collection_id={collection_id}",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["areas"][0]["why_detected"] == "No saved source matched Testing."
    assert use_case.received == {"user_id": user.id, "topic": "Python", "collection_id": collection_id}


def test_create_knowledge_gap_note_route_creates_note_from_gap_payload() -> None:
    user = _make_user()
    collection_id = uuid.uuid4()
    note_id = uuid.uuid4()
    use_case = _CreateGapNoteUseCase(
        NoteDTO(
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
    client = _client(user, {CreateKnowledgeGapNoteUseCase: use_case})

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
    assert use_case.received == {
        "user_id": user.id,
        "gap_id": "python--testing",
        "topic": "Python",
        "area_name": "Testing",
        "collection_id": collection_id,
    }


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


def _gap(collection_id: uuid.UUID | None = None) -> KnowledgeGapDTO:
    return KnowledgeGapDTO(
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
            KnowledgeGapAreaDTO(
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
