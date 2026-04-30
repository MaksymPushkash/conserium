import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.document_dtos import DocumentDTO, DocumentListDTO
from src.application.dtos.query_dtos import QueryDTO, QueryResultDTO, QuerySourceDTO
from src.application.dtos.query_stream_dtos import QueryStreamEventDTO, QueryStreamEventType
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.cache.document_status_cache import DocumentStatusDTO
from src.application.ports.ingestion.file_storage import IFileStorage, StoredFile
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.services.refrag.heuristic_context_builder import HeuristicRefragContextBuilder
from src.application.use_cases.documents.create_document_use_case import CreateDocumentUseCase
from src.application.use_cases.documents.delete_document_use_case import DeleteDocumentUseCase
from src.application.use_cases.documents.get_document_status_use_case import GetDocumentStatusUseCase
from src.application.use_cases.documents.get_document_use_case import GetDocumentUseCase
from src.application.use_cases.documents.ingest_document_use_case import IngestDocumentUseCase
from src.application.use_cases.documents.list_documents_use_case import ListDocumentsUseCase
from src.application.use_cases.query.query_use_case import QueryUseCase
from src.application.use_cases.query.stream_query_use_case import StreamQueryUseCase
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

    async def __call__(self, *args: object) -> object:
        self.received_dto = args[0] if len(args) == 1 else args
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


class _StreamingUseCase:
    def __init__(self, events: list[QueryStreamEventDTO]) -> None:
        self._events = events
        self.received_dto: object | None = None

    async def __call__(self, dto: object) -> object:
        self.received_dto = dto
        for event in self._events:
            yield event


class _FakeFileStorage:
    def __init__(self) -> None:
        self.saved_filename: str | None = None
        self.saved_content: bytes | None = None

    async def save_document_file(
        self,
        *,
        user_id: uuid.UUID,
        filename: str,
        content: bytes,
    ) -> StoredFile:
        self.saved_filename = filename
        self.saved_content = content
        return StoredFile(path=f"/tmp/{user_id}/{filename}", size_bytes=len(content))


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
    assert "raw_content" not in response.json()["items"][0]


def test_ingest_document_route_queues_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    document = DocumentDTO(
        id=document.id,
        user_id=document.user_id,
        collection_id=document.collection_id,
        title=document.title,
        type=document.type,
        status=DocumentStatus.QUEUED,
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
    client = _make_client(user, {IngestDocumentUseCase: use_case})

    try:
        response = client.post(
            "/api/v1/ingest",
            headers={"Authorization": "Bearer access-token"},
            json={"title": "Saved note", "raw_content": "Hello\n\nWorld", "type": "TEXT"},
        )
    finally:
        client.close()

    assert response.status_code == 202
    assert response.json()["id"] == str(document.id)
    assert response.json()["status"] == "QUEUED"
    assert use_case.received_dto is not None


def test_ingest_text_document_route_queues_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    document = DocumentDTO(
        id=document.id,
        user_id=document.user_id,
        collection_id=document.collection_id,
        title=document.title,
        type=document.type,
        status=DocumentStatus.QUEUED,
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
    client = _make_client(user, {IngestDocumentUseCase: use_case})

    try:
        response = client.post(
            "/api/v1/documents/ingest-text",
            headers={"Authorization": "Bearer access-token"},
            json={"title": "Saved note", "raw_text": "Hello\n\nWorld", "type": "TEXT"},
        )
    finally:
        client.close()

    assert response.status_code == 202
    assert response.json()["id"] == str(document.id)
    assert response.json()["status"] == "QUEUED"
    assert use_case.received_dto is not None


def test_ingest_pdf_document_route_stores_upload_and_queues_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    document = DocumentDTO(
        id=document.id,
        user_id=document.user_id,
        collection_id=document.collection_id,
        title="Uploaded report",
        type=DocumentType.PDF,
        status=DocumentStatus.QUEUED,
        source_url=None,
        file_path=f"/tmp/{user.id}/report.pdf",
        file_size_bytes=13,
        raw_content=None,
        summary=None,
        word_count=None,
        language="en",
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )
    use_case = _ReturningUseCase(document)
    storage = _FakeFileStorage()
    client = _make_client(user, {IngestDocumentUseCase: use_case, IFileStorage: storage})

    try:
        response = client.post(
            "/api/v1/documents/ingest/pdf",
            headers={"Authorization": "Bearer access-token"},
            data={"title": "Uploaded report", "language": "en"},
            files={"file": ("report.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    finally:
        client.close()

    assert response.status_code == 202
    assert response.json()["status"] == "QUEUED"
    assert storage.saved_filename == "report.pdf"
    assert storage.saved_content == b"%PDF-1.4 fake"
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


def test_get_document_status_route_returns_cached_status() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    status_dto = DocumentStatusDTO(
        document_id=document.id,
        status="PROCESSING",
        progress=40,
        message="Splitting into chunks.",
    )
    client = _make_client(user, {GetDocumentStatusUseCase: _ReturningUseCase(status_dto)})

    try:
        response = client.get(
            f"/api/v1/documents/{document.id}/status",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json() == {
        "document_id": str(document.id),
        "status": "PROCESSING",
        "progress": 40,
        "message": "Splitting into chunks.",
    }


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


def test_query_route_returns_sources() -> None:
    user = _make_user()
    conversation_id = uuid.uuid4()
    source = QuerySourceDTO(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Architecture Notes",
        content="Clean Architecture keeps dependencies pointing inward.",
        page_number=12,
        chunk_index=0,
        score=0.75,
    )
    use_case = _ReturningUseCase(
        QueryResultDTO(
            conversation_id=conversation_id,
            query="Clean Architecture",
            answer="Found relevant saved context.",
            sources=[source],
            refrag_context=HeuristicRefragContextBuilder().build_context(
                query="Clean Architecture",
                sources=[source],
            ),
        )
    )
    client = _make_client(user, {QueryUseCase: use_case})

    try:
        response = client.post(
            "/api/v1/query",
            headers={"Authorization": "Bearer access-token"},
            json={"query": "Clean Architecture", "conversation_id": str(conversation_id), "limit": 5},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["conversation_id"] == str(conversation_id)
    assert response.json()["sources"][0]["page_number"] == 12
    assert response.json()["sources"][0]["document_title"] == "Architecture Notes"
    assert response.json()["sources"][0]["citation"] == "[1]"
    assert response.json()["sources"][0]["content"] == source.content
    assert response.json()["refrag_context"]["full_text_chunks"][0]["representation"] == "FULL_TEXT"
    assert use_case.received_dto is not None
    assert cast("QueryDTO", use_case.received_dto).conversation_id == conversation_id


def test_query_stream_route_returns_sse_events() -> None:
    user = _make_user()
    conversation_id = uuid.uuid4()
    use_case = _StreamingUseCase(
        [
            QueryStreamEventDTO(
                event=QueryStreamEventType.METADATA,
                data={"query_id": "query-1", "query": "Clean Architecture", "sources": []},
            ),
            QueryStreamEventDTO(event=QueryStreamEventType.TOKEN, data={"text": "Hello"}),
            QueryStreamEventDTO(event=QueryStreamEventType.DONE, data={"query_id": "query-1"}),
        ]
    )
    client = _make_client(user, {StreamQueryUseCase: use_case})

    try:
        response = client.post(
            "/api/v1/query/stream",
            headers={"Authorization": "Bearer access-token"},
            json={"query": "Clean Architecture", "conversation_id": str(conversation_id), "limit": 5},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: metadata\ndata: {"query_id":"query-1","query":"Clean Architecture","sources":[]}' in response.text
    assert 'event: token\ndata: {"text":"Hello"}' in response.text
    assert 'event: done\ndata: {"query_id":"query-1"}' in response.text
    assert use_case.received_dto is not None
    assert cast("QueryDTO", use_case.received_dto).conversation_id == conversation_id
