import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.chat_dtos import ChatDetailDTO, ChatMessageDTO, ChatSessionDTO
from src.application.dtos.document_dtos import DocumentDTO, DocumentListDTO
from src.application.dtos.note_dtos import NoteDTO, NoteListDTO, NoteListItemDTO
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
from src.application.use_cases.documents.note_use_cases import (
    CreateNoteUseCase,
    DeleteNoteUseCase,
    GetNoteUseCase,
    ListNotesUseCase,
    UpdateNoteUseCase,
)
from src.application.use_cases.query.chat_use_cases import CreateChatUseCase, GetChatUseCase
from src.application.use_cases.query.query_use_case import QueryUseCase
from src.application.use_cases.query.stream_query_use_case import StreamQueryUseCase
from src.core.metrics import metrics_registry
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


class _KeywordNoneUseCase:
    def __init__(self) -> None:
        self.received_kwargs: dict[str, object] | None = None

    async def __call__(self, **kwargs: object) -> None:
        self.received_kwargs = kwargs


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

    async def read_document_file(self, path: str) -> bytes:
        return b""


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
    return DocumentDTO(entities=None, categories=None, 
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


def _make_note_dto(*, user_id: uuid.UUID) -> NoteDTO:
    return NoteDTO(
        id=uuid.uuid4(),
        title="Asyncio",
        content="Asyncio runs cooperative tasks on one event loop.",
        status=DocumentStatus.READY,
        word_count=8,
        language="en",
        created_at=datetime.now(UTC),
        updated_at=None,
    )


def _make_note_list_item_dto(note: NoteDTO) -> NoteListItemDTO:
    return NoteListItemDTO(
        id=note.id,
        title=note.title,
        status=note.status,
        word_count=note.word_count,
        language=note.language,
        created_at=note.created_at,
        updated_at=note.updated_at,
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
    document = DocumentDTO(entities=None, categories=None, 
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


def test_ingest_youtube_document_route_queues_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    document = DocumentDTO(entities=None, categories=None, 
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
    use_case = _ReturningUseCase(document)
    client = _make_client(user, {IngestDocumentUseCase: use_case})

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
    use_case = _ReturningUseCase(
        DocumentDTO(entities=None, categories=None, 
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
    client = _make_client(user, {IngestDocumentUseCase: use_case})

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
    assert "# HELP cortex_http_requests_total" in body
    assert "# HELP cortex_ingestion_latency_seconds" in body
    assert "# HELP cortex_queue_depth" in body
    assert "cortex_http_requests_total" in body
    assert metrics_registry.render_prometheus() == body


def test_ingest_text_document_route_queues_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    document = DocumentDTO(entities=None, categories=None, 
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
    document = DocumentDTO(entities=None, categories=None, 
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


def test_ingest_pdf_document_route_rejects_large_upload(monkeypatch) -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    use_case = _ReturningUseCase(document)
    storage = _FakeFileStorage()
    client = _make_client(user, {IngestDocumentUseCase: use_case, IFileStorage: storage})
    monkeypatch.setattr("src.presentation.api.v1.ingestion.settings.MAX_UPLOAD_BYTES", 4)

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
    assert use_case.received_dto is None


def test_ingest_audio_document_route_stores_upload_and_queues_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    document = DocumentDTO(entities=None, categories=None, 
        id=document.id,
        user_id=document.user_id,
        collection_id=document.collection_id,
        title="Uploaded audio",
        type=DocumentType.AUDIO,
        status=DocumentStatus.QUEUED,
        source_url=None,
        file_path=f"/tmp/{user.id}/voice.m4a",
        file_size_bytes=9,
        raw_content=None,
        summary=None,
        word_count=None,
        language="uk",
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
            "/api/v1/ingest/audio",
            headers={"Authorization": "Bearer access-token"},
            data={"title": "Uploaded audio", "language": "uk"},
            files={"file": ("voice.m4a", b"audiofake", "audio/mp4")},
        )
    finally:
        client.close()

    assert response.status_code == 202
    assert response.json()["status"] == "QUEUED"
    assert response.json()["type"] == "AUDIO"
    assert storage.saved_filename == "voice.m4a"
    assert storage.saved_content == b"audiofake"
    assert use_case.received_dto is not None


def test_ingest_image_document_route_stores_upload_and_queues_document() -> None:
    user = _make_user()
    document = _make_document_dto(user_id=user.id)
    document = DocumentDTO(entities=None, categories=None, 
        id=document.id,
        user_id=document.user_id,
        collection_id=document.collection_id,
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
    use_case = _ReturningUseCase(document)
    storage = _FakeFileStorage()
    client = _make_client(user, {IngestDocumentUseCase: use_case, IFileStorage: storage})

    try:
        response = client.post(
            "/api/v1/ingest/image",
            headers={"Authorization": "Bearer access-token"},
            data={"title": "Uploaded image", "language": "en"},
            files={"file": ("scan.png", b"imagefake", "image/png")},
        )
    finally:
        client.close()

    assert response.status_code == 202
    assert response.json()["status"] == "QUEUED"
    assert response.json()["type"] == "IMAGE"
    assert storage.saved_filename == "scan.png"
    assert storage.saved_content == b"imagefake"
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


def test_create_note_route_returns_note() -> None:
    user = _make_user()
    note = _make_note_dto(user_id=user.id)
    use_case = _ReturningUseCase(note)
    client = _make_client(user, {CreateNoteUseCase: use_case})

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
    assert use_case.received_dto is not None


def test_list_notes_route_returns_notes() -> None:
    user = _make_user()
    note = _make_note_dto(user_id=user.id)
    use_case = _ReturningUseCase(NoteListDTO(items=[_make_note_list_item_dto(note)], total=1, limit=100, offset=0))
    client = _make_client(user, {ListNotesUseCase: use_case})

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
    client = _make_client(user, {GetNoteUseCase: _ReturningUseCase(note)})

    try:
        response = client.get(f"/api/v1/notes/{note.id}", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["title"] == "Asyncio"


def test_update_note_route_returns_updated_note() -> None:
    user = _make_user()
    note = _make_note_dto(user_id=user.id)
    use_case = _ReturningUseCase(note)
    client = _make_client(user, {UpdateNoteUseCase: use_case})

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
    assert use_case.received_dto is not None


def test_delete_note_route_returns_no_content() -> None:
    user = _make_user()
    note_id = uuid.uuid4()
    use_case = _KeywordNoneUseCase()
    client = _make_client(user, {DeleteNoteUseCase: use_case})

    try:
        response = client.delete(f"/api/v1/notes/{note_id}", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 204
    assert response.content == b""
    assert use_case.received_kwargs == {"user_id": user.id, "note_id": note_id}


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


def test_create_chat_route_returns_chat_session() -> None:
    user = _make_user()
    chat = ChatSessionDTO(
        id=uuid.uuid4(),
        user_id=user.id,
        title="Python learning",
        message_count=0,
        created_at=datetime.now(UTC),
        updated_at=None,
    )
    use_case = _ReturningUseCase(chat)
    client = _make_client(user, {CreateChatUseCase: use_case})

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
    assert use_case.received_dto is not None


def test_get_chat_route_returns_saved_messages() -> None:
    user = _make_user()
    chat_id = uuid.uuid4()
    created_at = datetime.now(UTC)
    chat = ChatSessionDTO(
        id=chat_id,
        user_id=user.id,
        title="Python learning",
        message_count=2,
        created_at=created_at,
        updated_at=created_at,
    )
    use_case = _ReturningUseCase(
        ChatDetailDTO(
            session=chat,
            messages=[
                ChatMessageDTO(
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
                ChatMessageDTO(
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
    client = _make_client(user, {GetChatUseCase: use_case})

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
