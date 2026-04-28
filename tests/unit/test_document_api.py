import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.document_dtos import DocumentDTO, DocumentListDTO
from src.application.interfaces.jwt_service import IJWTService
from src.application.interfaces.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.create_document_use_case import CreateDocumentUseCase
from src.application.use_cases.documents.delete_document_use_case import DeleteDocumentUseCase
from src.application.use_cases.documents.get_document_use_case import GetDocumentUseCase
from src.application.use_cases.documents.ingest_text_document_use_case import IngestTextDocumentUseCase
from src.application.use_cases.documents.list_documents_use_case import ListDocumentsUseCase
from src.domain.entities.user_entity import UserEntity
from src.domain.exceptions import DocumentNotFoundException
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


class _ReturningUseCase:
    def __init__(self, result: object) -> None:
        self._result = result
        self.received_dto: object | None = None

    async def __call__(self, dto: object) -> object:
        self.received_dto = dto
        return self._result


class _NoneUseCase:
    def __init__(self) -> None:
        self.received_dto: object | None = None

    async def __call__(self, dto: object) -> None:
        self.received_dto = dto


class _RaisingUseCase:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def __call__(self, dto: object) -> object:
        raise self._exc


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


def _make_document_dto(*, user_id: uuid.UUID) -> DocumentDTO:
    return DocumentDTO(
        id=uuid.uuid4(),
        user_id=user_id,
        collection_id=None,
        title="Saved note",
        type=DocumentType.TEXT,
        status=DocumentStatus.PENDING,
        source_url=None,
        file_path=None,
        file_size_bytes=None,
        raw_content="Hello",
        summary=None,
        word_count=1,
        language="en",
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=datetime.now(UTC),
        updated_at=None,
    )


def _make_client(user: UserEntity, dependencies: Mapping[type[object], object]) -> TestClient:
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


def test_create_document_route_returns_created_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    use_case = _ReturningUseCase(document)
    client = _make_client(user, {CreateDocumentUseCase: use_case})

    try:
        response = client.post(
            "/api/v1/documents",
            headers={"Authorization": "Bearer access-token"},
            json={"title": "Saved note", "type": "TEXT", "raw_content": "Hello"},
        )
    finally:
        client.close()

    assert response.status_code == 201
    assert response.json()["id"] == str(document.id)
    assert response.json()["status"] == "PENDING"
    assert use_case.received_dto is not None


def test_list_documents_route_returns_document_list() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    use_case = _ReturningUseCase(DocumentListDTO(items=[document], total=1, limit=10, offset=0))
    client = _make_client(user, {ListDocumentsUseCase: use_case})

    try:
        response = client.get(
            "/api/v1/documents?limit=10&offset=0",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == str(document.id)


def test_ingest_text_document_route_returns_ready_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    document = DocumentDTO(
        id=document.id,
        user_id=document.user_id,
        collection_id=document.collection_id,
        title=document.title,
        type=document.type,
        status=DocumentStatus.READY,
        source_url=document.source_url,
        file_path=document.file_path,
        file_size_bytes=document.file_size_bytes,
        raw_content=document.raw_content,
        summary=document.summary,
        word_count=document.word_count,
        language=document.language,
        is_duplicate=document.is_duplicate,
        duplicate_of_id=document.duplicate_of_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )
    use_case = _ReturningUseCase(document)
    client = _make_client(user, {IngestTextDocumentUseCase: use_case})

    try:
        response = client.post(
            "/api/v1/documents/ingest-text",
            headers={"Authorization": "Bearer access-token"},
            json={"title": "Saved note", "raw_text": "Hello\n\nWorld", "type": "TEXT"},
        )
    finally:
        client.close()

    assert response.status_code == 201
    assert response.json()["id"] == str(document.id)
    assert response.json()["status"] == "READY"
    assert use_case.received_dto is not None


def test_get_document_route_returns_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    client = _make_client(user, {GetDocumentUseCase: _ReturningUseCase(document)})

    try:
        response = client.get(f"/api/v1/documents/{document.id}", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["id"] == str(document.id)


def test_get_document_route_maps_not_found() -> None:
    user = _make_user()
    client = _make_client(user, {GetDocumentUseCase: _RaisingUseCase(DocumentNotFoundException("document not found"))})

    try:
        response = client.get(f"/api/v1/documents/{uuid.uuid4()}", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 404
    assert response.json() == {"detail": "document not found"}


def test_delete_document_route_returns_no_content() -> None:
    user = _make_user()
    use_case = _NoneUseCase()
    client = _make_client(user, {DeleteDocumentUseCase: use_case})

    try:
        response = client.delete(f"/api/v1/documents/{uuid.uuid4()}", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 204
    assert response.content == b""
    assert use_case.received_dto is not None
