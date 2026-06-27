import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from src.auth.jwt_service import JWTService
from src.chats.repository import ChatDetailRecord, ChatMessageRecord, ChatSessionRecord
from src.chats.service import get_chat_service, to_chat_detail_response, to_chat_session_response
from src.collections.endpoints import get_collection_service
from src.collections.schemas import CollectionListResponse, CollectionResponse
from src.documents.dependencies import get_document_service
from src.documents.ingestion import DocumentIngester
from src.documents.note_dependencies import get_note_service
from src.documents.notes import NoteService
from src.documents.schemas import (
    DocumentConnection,
    DocumentConnectionsResult,
    DocumentListResult,
    DocumentResult,
    DocumentSearchResult,
    DocumentSearchResults,
    NoteListItemResponse,
    NoteListResponse,
    NoteResponse,
)
from src.documents.service import DocumentService
from src.documents.status import DocumentStatus
from src.documents.status_cache import DocumentStatusSnapshot
from src.documents.status_service import DocumentStatusService
from src.documents.types import DocumentType
from src.ingestion.dependencies import get_document_status_service
from src.kit.exceptions import DocumentNotFoundException, ValidationException
from src.kit.storage.file_storage import FileStorage, StoredFile
from src.main import create_app
from src.models.user import UserModel
from src.observability.metrics_registry import metrics_registry
from src.postgres import get_db_read_session, get_db_session
from src.query.dependencies import get_query_executor, get_stream_query_executor
from src.query.schemas import QueryInput, QueryResult, QuerySource, QueryStreamEvent, QueryStreamEventType
from src.query.services.refrag.heuristic_context_builder import HeuristicRefragContextBuilder
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


class _DocumentServiceOverride:
    def __init__(self, handler: Any) -> None:
        self._handler = handler

    async def create(self, *args: object, **kwargs: object) -> object:
        return await self._handler(*args, **kwargs)

    async def list(self, *args: object, **kwargs: object) -> object:
        return await self._handler(*args, **kwargs)

    async def search(self, *args: object, **kwargs: object) -> object:
        return await self._handler(*args, **kwargs)

    async def get(self, *args: object, **kwargs: object) -> object:
        return await self._handler(*args, **kwargs)

    async def connections(self, *args: object, **kwargs: object) -> object:
        return await self._handler(*args, **kwargs)

    async def delete(self, *args: object, **kwargs: object) -> None:
        await self._handler(*args, **kwargs)

    async def bulk_move(self, *args: object, **kwargs: object) -> None:
        await self._handler(*args, **kwargs)

    async def bulk_add_tags(self, *args: object, **kwargs: object) -> None:
        await self._handler(*args, **kwargs)


class _DocumentStatusServiceOverride:
    def __init__(self, handler: Any) -> None:
        self._handler = handler

    async def get(self, document_id: uuid.UUID, user_id: uuid.UUID) -> object:
        return await self._handler(document_id, user_id)


class _NoteServiceOverride:
    def __init__(self, handler: Any) -> None:
        self._handler = handler

    async def create(self, *args: object, **kwargs: object) -> object:
        return await self._handler(*args, **kwargs)

    async def list(self, *args: object, **kwargs: object) -> object:
        return await self._handler(*args, **kwargs)

    async def get(self, *args: object, **kwargs: object) -> object:
        return await self._handler(*args, **kwargs)

    async def update(self, *args: object, **kwargs: object) -> object:
        return await self._handler(*args, **kwargs)

    async def delete(self, *, user_id: uuid.UUID, note_id: uuid.UUID) -> None:
        await self._handler(user_id=user_id, note_id=note_id)


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


class _ReturningCollectionService:
    def __init__(self, result: CollectionListResponse) -> None:
        self._result = result
        self.received: dict[str, object] | None = None

    async def list(self, session: object, **kwargs: object):
        self.received = kwargs
        return self._result


class _ReturningChatService:
    def __init__(self, result: object) -> None:
        self._result = result
        self.received: dict[str, object] | None = None

    async def create(self, session: object, **kwargs: object):
        self.received = kwargs
        return to_chat_session_response(cast("ChatSessionRecord", self._result))

    async def get(self, session: object, **kwargs: object):
        self.received = kwargs
        return to_chat_detail_response(cast("ChatDetailRecord", self._result))


async def _session_override():
    yield object()


class _ReturningService:
    def __init__(self, result: object) -> None:
        self._result = result
        self.received_dto: object | None = None
        self.received_kwargs: dict[str, object] = {}

    async def __call__(self, *args: object, **kwargs: object) -> object:
        self.received_dto = args[0] if len(args) == 1 else args
        self.received_kwargs = kwargs
        return self._result


class _NoneService:
    def __init__(self) -> None:
        self.received_dto: object | None = None
        self.received_kwargs: dict[str, object] = {}

    async def __call__(self, *args: object, **kwargs: object) -> None:
        self.received_dto = args[0] if len(args) == 1 else args
        self.received_kwargs = kwargs


class _KeywordNoneService:
    def __init__(self) -> None:
        self.received_kwargs: dict[str, object] | None = None

    async def __call__(self, **kwargs: object) -> None:
        self.received_kwargs = kwargs


class _RaisingService:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.received_dto: object | None = None
        self.received_kwargs: dict[str, object] = {}

    async def __call__(self, *args: object, **kwargs: object) -> object:
        self.received_dto = args[0] if len(args) == 1 else args
        self.received_kwargs = kwargs
        raise self._exc


class _StreamingService:
    def __init__(self, events: list[QueryStreamEvent]) -> None:
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

    async def read_document_file(self, path: str) -> bytes:
        return b""


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


def _make_document_dto(*, user_id: uuid.UUID, suggested_questions: list[str] | None = None) -> DocumentResult:
    return DocumentResult(
        entities=None,
        categories=None,
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
        suggested_questions=suggested_questions or [],
        word_count=1,
        language="en",
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=datetime.now(UTC),
        updated_at=None,
    )


def _make_note_dto(*, user_id: uuid.UUID) -> NoteResponse:
    return NoteResponse(
        id=uuid.uuid4(),
        collection_id=None,
        title="Asyncio",
        content="Asyncio runs cooperative tasks on one event loop.",
        status=DocumentStatus.READY,
        word_count=8,
        language="en",
        created_at=datetime.now(UTC),
        updated_at=None,
    )


def _make_note_list_item_dto(note: NoteResponse) -> NoteListItemResponse:
    return NoteListItemResponse(
        id=note.id,
        collection_id=note.collection_id,
        title=note.title,
        status=note.status,
        word_count=note.word_count,
        language=note.language,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _make_client(user: UserModel, dependencies: Mapping[type[object], object]) -> TestClient:
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
    document_service = dependencies.get(DocumentService)
    if document_service is not None:
        app.dependency_overrides[get_document_service] = lambda: document_service
    note_service = dependencies.get(NoteService)
    if note_service is not None:
        app.dependency_overrides[get_note_service] = lambda: note_service
    return TestClient(app, raise_server_exceptions=False)


def test_create_document_route_returns_created_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    handler = _ReturningService(document)
    client = _make_client(user, {DocumentService: _DocumentServiceOverride(handler)})

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
    assert handler.received_dto is not None


def test_list_documents_route_returns_document_list() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    handler = _ReturningService(DocumentListResult(items=[document], total=1, limit=10, offset=0))
    client = _make_client(user, {DocumentService: _DocumentServiceOverride(handler)})

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


def test_search_documents_route_returns_semantic_results() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    chunk_id = uuid.uuid4()
    handler = _ReturningService(
        DocumentSearchResults(
            items=[
                DocumentSearchResult(
                    document=document,
                    snippet="asyncio overlaps I/O operations with coroutines.",
                    score=0.91,
                    chunk_id=chunk_id,
                    page_number=None,
                )
            ],
            query="parallel requests",
            total=1,
            limit=20,
        )
    )
    client = _make_client(user, {DocumentService: _DocumentServiceOverride(handler)})

    try:
        response = client.get(
            "/api/v1/documents/search?query=parallel%20requests&limit=20&type=TEXT&status=PENDING&tag=python",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["document"]["id"] == str(document.id)
    assert response.json()["items"][0]["snippet"] == "asyncio overlaps I/O operations with coroutines."
    assert response.json()["items"][0]["chunk_id"] == str(chunk_id)
    assert handler.received_dto is not None


def test_ingest_document_route_queues_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    document = DocumentResult(
        entities=None,
        categories=None,
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
    handler = _ReturningService(document)
    client = _make_client(user, {DocumentIngester: handler})

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
    assert handler.received_dto is not None


def test_ingest_youtube_document_route_queues_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    document = DocumentResult(
        entities=None,
        categories=None,
        id=document.id,
        user_id=document.user_id,
        collection_id=document.collection_id,
        title="Saved video",
        type=DocumentType.YOUTUBE,
        status=DocumentStatus.QUEUED,
        source_url="https://youtu.be/abc123",
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
    handler = _ReturningService(document)
    client = _make_client(user, {DocumentIngester: handler})

    try:
        response = client.post(
            "/api/v1/ingest",
            headers={"Authorization": "Bearer access-token"},
            json={"title": "Saved video", "source_url": "https://youtu.be/abc123", "type": "YOUTUBE"},
        )
    finally:
        client.close()

    assert response.status_code == 202
    assert response.json()["type"] == "YOUTUBE"
    assert response.json()["status"] == "QUEUED"


def test_metrics_endpoint_returns_prometheus_text() -> None:
    metrics_registry.reset_for_tests()
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    handler = _ReturningService(
        DocumentResult(
            entities=None,
            categories=None,
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
    )
    client = _make_client(user, {DocumentIngester: handler})

    try:
        client.post(
            "/api/v1/ingest",
            headers={"Authorization": "Bearer access-token"},
            json={"title": "Saved note", "raw_content": "Hello\n\nWorld", "type": "TEXT"},
        )
        response = client.get("/metrics")
    finally:
        client.close()

    body = response.text
    assert response.status_code == 200
    assert "# HELP conserium_http_requests_total" in body
    assert "# HELP conserium_ingestion_latency_seconds" in body
    assert "# HELP conserium_queue_depth" in body
    assert "conserium_http_requests_total" in body
    assert metrics_registry.render_prometheus() == body


def test_ingest_text_document_route_queues_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    document = DocumentResult(
        entities=None,
        categories=None,
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
    handler = _ReturningService(document)
    client = _make_client(user, {DocumentIngester: handler})

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
    assert handler.received_dto is not None


def test_list_collections_route_accepts_workspace_filter() -> None:
    user = _make_user()
    workspace_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    collection = CollectionResponse(
        id=collection_id,
        user_id=user.id,
        workspace_id=workspace_id,
        access_role="owner",
        name="Shared",
        description=None,
        color=None,
        created_at=datetime.now(UTC),
        updated_at=None,
    )
    service = _ReturningCollectionService(CollectionListResponse(items=[collection], total=1, limit=25, offset=5))
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer({JWTService: jwt_service, UserRepository: _FakeRepositorySession(user)})._dependencies)
    app.dependency_overrides[get_collection_service] = lambda: service
    app.dependency_overrides[get_db_read_session] = _session_override
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get(
            f"/api/v1/collections?limit=25&offset=5&workspace_id={workspace_id}",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["workspace_id"] == str(workspace_id)
    assert service.received is not None
    assert service.received["workspace_id"] == workspace_id


def test_ingest_pdf_document_route_stores_upload_and_queues_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    collection_id = uuid.uuid4()
    document = DocumentResult(
        entities=None,
        categories=None,
        id=document.id,
        user_id=document.user_id,
        collection_id=collection_id,
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
    handler = _ReturningService(document)
    storage = _FakeFileStorage()
    client = _make_client(user, {DocumentIngester: handler, FileStorage: storage})

    try:
        response = client.post(
            "/api/v1/documents/ingest/pdf",
            headers={"Authorization": "Bearer access-token"},
            data={"title": "Uploaded report", "language": "en", "collection_id": str(document.collection_id)},
            files={"file": ("report.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    finally:
        client.close()

    assert response.status_code == 202
    assert response.json()["status"] == "QUEUED"
    assert storage.saved_filename == "report.pdf"
    assert storage.saved_content == b"%PDF-1.4 fake"
    assert handler.received_kwargs["collection_id"] == document.collection_id


def test_ingest_pdf_document_route_rejects_large_upload(monkeypatch: MonkeyPatch) -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    handler = _ReturningService(document)
    storage = _FakeFileStorage()
    client = _make_client(user, {DocumentIngester: handler, FileStorage: storage})
    monkeypatch.setattr("src.ingestion.endpoints.settings.MAX_UPLOAD_BYTES", 4)

    try:
        response = client.post(
            "/api/v1/documents/ingest/pdf",
            headers={"Authorization": "Bearer access-token"},
            data={"title": "Uploaded report", "language": "en"},
            files={"file": ("report.pdf", b"too-large", "application/pdf")},
        )
    finally:
        client.close()

    assert response.status_code == 413
    assert storage.saved_content is None
    assert handler.received_dto is None


def test_ingest_image_document_route_stores_upload_and_queues_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    collection_id = uuid.uuid4()
    document = DocumentResult(
        entities=None,
        categories=None,
        id=document.id,
        user_id=document.user_id,
        collection_id=collection_id,
        title="Uploaded image",
        type=DocumentType.IMAGE,
        status=DocumentStatus.QUEUED,
        source_url=None,
        file_path=f"/tmp/{user.id}/scan.png",
        file_size_bytes=12,
        raw_content=None,
        summary=None,
        word_count=None,
        language="en",
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )
    handler = _ReturningService(document)
    storage = _FakeFileStorage()
    client = _make_client(user, {DocumentIngester: handler, FileStorage: storage})

    try:
        response = client.post(
            "/api/v1/ingest/image",
            headers={"Authorization": "Bearer access-token"},
            data={"title": "Uploaded image", "language": "en", "collection_id": str(document.collection_id)},
            files={"file": ("scan.png", b"imagefake", "image/png")},
        )
    finally:
        client.close()

    assert response.status_code == 202
    assert response.json()["status"] == "QUEUED"
    assert response.json()["type"] == "IMAGE"
    assert storage.saved_filename == "scan.png"
    assert storage.saved_content == b"imagefake"
    assert handler.received_kwargs["collection_id"] == document.collection_id


def test_shared_pdf_upload_route_surfaces_workspace_role_denial() -> None:
    user = _make_user()
    collection_id = uuid.uuid4()
    handler = _RaisingService(ValidationException("workspace viewer cannot ingest into collection"))
    storage = _FakeFileStorage()
    client = _make_client(user, {DocumentIngester: handler, FileStorage: storage})

    try:
        response = client.post(
            "/api/v1/documents/ingest/pdf",
            headers={"Authorization": "Bearer access-token"},
            data={"title": "Shared report", "language": "en", "collection_id": str(collection_id)},
            files={"file": ("shared.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    finally:
        client.close()

    assert response.status_code == 422
    assert response.json() == {"detail": "workspace viewer cannot ingest into collection"}
    assert storage.saved_filename == "shared.pdf"
    assert handler.received_kwargs["collection_id"] == collection_id


def test_shared_image_upload_route_surfaces_workspace_role_denial() -> None:
    user = _make_user()
    collection_id = uuid.uuid4()
    handler = _RaisingService(ValidationException("workspace viewer cannot ingest into collection"))
    storage = _FakeFileStorage()
    client = _make_client(user, {DocumentIngester: handler, FileStorage: storage})

    try:
        response = client.post(
            "/api/v1/ingest/image",
            headers={"Authorization": "Bearer access-token"},
            data={"title": "Shared scan", "language": "en", "collection_id": str(collection_id)},
            files={"file": ("shared.png", b"imagefake", "image/png")},
        )
    finally:
        client.close()

    assert response.status_code == 422
    assert response.json() == {"detail": "workspace viewer cannot ingest into collection"}
    assert storage.saved_filename == "shared.png"
    assert handler.received_kwargs["collection_id"] == collection_id


def test_get_document_route_returns_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    client = _make_client(user, {DocumentService: _DocumentServiceOverride(_ReturningService(document))})

    try:
        response = client.get(f"/api/v1/documents/{document.id}", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["id"] == str(document.id)


def test_get_document_suggested_questions_route_returns_questions() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id, suggested_questions=["What is FastAPI?", "How is it tested?"])
    client = _make_client(user, {DocumentService: _DocumentServiceOverride(_ReturningService(document))})

    try:
        response = client.get(
            f"/api/v1/documents/{document.id}/suggested-questions",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json() == ["What is FastAPI?", "How is it tested?"]


def test_get_document_connections_route_returns_related_documents() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    related = _make_document_dto(user_id=user.id)
    result = DocumentConnectionsResult(
        document_id=document.id,
        total=1,
        limit=3,
        items=[
            DocumentConnection(
                document=related,
                reasons=["Shared tags: python", "Same collection"],
                relationship_score=5,
            )
        ],
    )
    handler = _ReturningService(result)
    client = _make_client(user, {DocumentService: _DocumentServiceOverride(handler)})

    try:
        response = client.get(
            f"/api/v1/documents/{document.id}/connections?limit=3",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["document_id"] == str(document.id)
    assert response.json()["items"][0]["document"]["id"] == str(related.id)
    assert response.json()["items"][0]["reasons"] == ["Shared tags: python", "Same collection"]
    assert response.json()["items"][0]["relationship_score"] == 5
    assert handler.received_kwargs == {"user_id": user.id, "document_id": document.id, "limit": 3}


def test_get_document_status_route_returns_cached_status() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    status_dto = DocumentStatusSnapshot(
        document_id=document.id,
        status="PROCESSING",
        progress=40,
        message="Splitting into chunks.",
    )
    status_service = _DocumentStatusServiceOverride(_ReturningService(status_dto))
    client = _make_client(user, {DocumentStatusService: status_service})
    client.app.dependency_overrides[get_document_status_service] = lambda: status_service

    try:
        response = client.get(
            f"/api/v1/documents/{document.id}/status",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["document_id"] == str(document.id)
    assert response.json()["status"] == "PROCESSING"
    assert response.json()["progress"] == 40
    assert response.json()["message"] == "Splitting into chunks."
    assert response.json()["failure_reason"] is None
    assert response.json()["timeline"] == []


def test_get_document_route_maps_not_found() -> None:
    user = _make_user()
    client = _make_client(
        user,
        {DocumentService: _DocumentServiceOverride(_RaisingService(DocumentNotFoundException("document not found")))},
    )

    try:
        response = client.get(f"/api/v1/documents/{uuid.uuid4()}", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 404
    assert response.json() == {"detail": "document not found"}


def test_delete_document_route_returns_no_content() -> None:
    user = _make_user()
    handler = _NoneService()
    client = _make_client(user, {DocumentService: _DocumentServiceOverride(handler)})

    try:
        response = client.delete(f"/api/v1/documents/{uuid.uuid4()}", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 204
    assert response.content == b""
    assert handler.received_dto is not None


def test_bulk_move_documents_route_passes_collection_scope() -> None:
    user = _make_user()
    collection_id = uuid.uuid4()
    document_ids = [uuid.uuid4(), uuid.uuid4()]
    handler = _NoneService()
    client = _make_client(user, {DocumentService: _DocumentServiceOverride(handler)})

    try:
        response = client.post(
            "/api/v1/documents/bulk/move",
            headers={"Authorization": "Bearer access-token"},
            json={"document_ids": [str(document_id) for document_id in document_ids], "collection_id": str(collection_id)},
        )
    finally:
        client.close()

    assert response.status_code == 204
    assert handler.received_kwargs["document_ids"] == document_ids
    assert handler.received_kwargs["collection_id"] == collection_id


def test_bulk_add_document_tags_route_passes_tags() -> None:
    user = _make_user()
    document_ids = [uuid.uuid4()]
    handler = _NoneService()
    client = _make_client(user, {DocumentService: _DocumentServiceOverride(handler)})

    try:
        response = client.post(
            "/api/v1/documents/bulk/tags",
            headers={"Authorization": "Bearer access-token"},
            json={"document_ids": [str(document_ids[0])], "tags": ["python", "architecture"]},
        )
    finally:
        client.close()

    assert response.status_code == 204
    body = handler.received_kwargs["body"]
    assert body.document_ids == document_ids
    assert body.tags == ["python", "architecture"]


def test_create_note_route_returns_note() -> None:
    user = _make_user()
    note = _make_note_dto(user_id=user.id)
    handler = _ReturningService(note)
    client = _make_client(user, {NoteService: _NoteServiceOverride(handler)})

    try:
        response = client.post(
            "/api/v1/notes",
            headers={"Authorization": "Bearer access-token"},
            json={"title": "Asyncio", "content": "Asyncio runs cooperative tasks on one event loop.", "language": "en"},
        )
    finally:
        client.close()

    assert response.status_code == 201
    assert response.json()["id"] == str(note.id)
    assert response.json()["title"] == "Asyncio"
    assert response.json()["content"] == note.content
    assert handler.received_dto is not None


def test_list_notes_route_returns_notes() -> None:
    user = _make_user()
    note = _make_note_dto(user_id=user.id)
    handler = _ReturningService(NoteListResponse(items=[_make_note_list_item_dto(note)], total=1, limit=100, offset=0))
    client = _make_client(user, {NoteService: _NoteServiceOverride(handler)})

    try:
        response = client.get("/api/v1/notes", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == str(note.id)
    assert "content" not in response.json()["items"][0]


def test_get_note_route_returns_note() -> None:
    user = _make_user()
    note = _make_note_dto(user_id=user.id)
    client = _make_client(user, {NoteService: _NoteServiceOverride(_ReturningService(note))})

    try:
        response = client.get(f"/api/v1/notes/{note.id}", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["title"] == "Asyncio"


def test_update_note_route_returns_updated_note() -> None:
    user = _make_user()
    note = _make_note_dto(user_id=user.id)
    handler = _ReturningService(note)
    client = _make_client(user, {NoteService: _NoteServiceOverride(handler)})

    try:
        response = client.patch(
            f"/api/v1/notes/{note.id}",
            headers={"Authorization": "Bearer access-token"},
            json={"title": "Asyncio", "content": "Asyncio runs cooperative tasks on one event loop.", "language": "en"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["id"] == str(note.id)
    assert handler.received_dto is not None


def test_delete_note_route_returns_no_content() -> None:
    user = _make_user()
    note_id = uuid.uuid4()
    handler = _KeywordNoneService()
    client = _make_client(user, {NoteService: _NoteServiceOverride(handler)})

    try:
        response = client.delete(f"/api/v1/notes/{note_id}", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 204
    assert response.content == b""
    assert handler.received_kwargs == {"user_id": user.id, "note_id": note_id}


def test_query_route_returns_sources() -> None:
    user = _make_user()
    conversation_id = uuid.uuid4()
    source = QuerySource(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Architecture Notes",
        content="Clean Architecture keeps dependencies pointing inward.",
        page_number=12,
        chunk_index=0,
        score=0.75,
    )
    handler = _ReturningService(
        QueryResult(
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
    client = _make_client(user, {})
    client.app.dependency_overrides[get_query_executor] = lambda: handler

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
    assert handler.received_dto is not None
    assert cast("QueryInput", handler.received_dto).conversation_id == conversation_id


def test_query_stream_route_returns_sse_events() -> None:
    user = _make_user()
    conversation_id = uuid.uuid4()
    handler = _StreamingService(
        [
            QueryStreamEvent(
                event=QueryStreamEventType.METADATA,
                data={"query_id": "query-1", "query": "Clean Architecture", "sources": []},
            ),
            QueryStreamEvent(event=QueryStreamEventType.TOKEN, data={"text": "Hello"}),
            QueryStreamEvent(event=QueryStreamEventType.DONE, data={"query_id": "query-1"}),
        ]
    )
    client = _make_client(user, {})
    client.app.dependency_overrides[get_stream_query_executor] = lambda: handler

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
    assert handler.received_dto is not None
    assert cast("QueryInput", handler.received_dto).conversation_id == conversation_id


def test_create_chat_route_returns_chat_session() -> None:
    user = _make_user()
    chat = ChatSessionRecord(
        id=uuid.uuid4(),
        user_id=user.id,
        title="Python learning",
        message_count=0,
        created_at=datetime.now(UTC),
        updated_at=None,
    )
    service = _ReturningChatService(chat)
    client = _make_client(user, {})
    client.app.dependency_overrides[get_chat_service] = lambda: service
    client.app.dependency_overrides[get_db_session] = _session_override

    try:
        response = client.post(
            "/api/v1/chats",
            headers={"Authorization": "Bearer access-token"},
            json={"title": "Python learning"},
        )
    finally:
        client.close()

    assert response.status_code == 201
    assert response.json()["id"] == str(chat.id)
    assert response.json()["title"] == "Python learning"
    assert response.json()["message_count"] == 0
    assert service.received == {"user_id": user.id, "title": "Python learning"}


def test_get_chat_route_returns_saved_messages() -> None:
    user = _make_user()
    chat_id = uuid.uuid4()
    created_at = datetime.now(UTC)
    chat = ChatSessionRecord(
        id=chat_id,
        user_id=user.id,
        title="Python learning",
        message_count=2,
        created_at=created_at,
        updated_at=created_at,
    )
    service = _ReturningChatService(
        ChatDetailRecord(
            session=chat,
            messages=[
                ChatMessageRecord(
                    id=uuid.uuid4(),
                    chat_id=chat_id,
                    role="user",
                    content="What is a decorator?",
                    sources=None,
                    refrag_context=None,
                    eval_scores=None,
                    trace_id=None,
                    created_at=created_at,
                ),
                ChatMessageRecord(
                    id=uuid.uuid4(),
                    chat_id=chat_id,
                    role="assistant",
                    content="A decorator wraps a function.",
                    sources=[],
                    refrag_context=None,
                    eval_scores={"faithfulness": 1.0},
                    trace_id="trace-1",
                    created_at=created_at,
                ),
            ],
        )
    )
    client = _make_client(user, {})
    client.app.dependency_overrides[get_chat_service] = lambda: service
    client.app.dependency_overrides[get_db_read_session] = _session_override

    try:
        response = client.get(
            f"/api/v1/chats/{chat_id}",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["session"]["title"] == "Python learning"
    assert response.json()["messages"][0]["content"] == "What is a decorator?"
    assert response.json()["messages"][1]["trace_id"] == "trace-1"
    assert service.received == {"user_id": user.id, "chat_id": chat_id}
