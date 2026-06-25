import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from src.collections.schemas import CollectionListResponse, CollectionResponse
from src.collections.service import CollectionService
from src.documents.ingestion import (
    ExternalIntakeService,
    ExternalItemIngester,
)
from src.documents.schemas import DocumentResult, ExternalIngestResult, ExternalIntakeItem
from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.integrations.schemas import ApiKeyPrincipal
from src.integrations.service import ApiKeyAuthenticator
from src.main import create_app
from src.query.schemas import QueryPayload, QueryResult, RefragContextPackage
from src.query.service import QueryExecutor
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


class _AuthenticateApiKey:
    def __init__(self, user_id: uuid.UUID, api_key_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.api_key_id = api_key_id
        self.received: tuple[str, str] | None = None

    async def __call__(self, token: str, *, required_scope: str) -> ApiKeyPrincipal:
        self.received = (token, required_scope)
        return ApiKeyPrincipal(user_id=self.user_id, api_key_id=self.api_key_id, scopes=[required_scope])


class _IngestExternalItem:
    def __init__(self, result: ExternalIngestResult) -> None:
        self.result = result
        self.received = None

    async def __call__(self, **kwargs):
        self.received = kwargs
        return self.result


class _ExternalIntakeService:
    def __init__(self, item: ExternalIntakeItem, result: ExternalIngestResult) -> None:
        self.item = item
        self.result = result
        self.received: tuple[uuid.UUID, int, int] | None = None

    async def list(self, *, user_id: uuid.UUID, limit: int = 20, offset: int = 0) -> list[ExternalIntakeItem]:
        self.received = (user_id, limit, offset)
        return [self.item]

    async def get(self, *, user_id: uuid.UUID, intake_item_id: uuid.UUID) -> ExternalIngestResult:
        return self.result

    async def retry(self, *, user_id: uuid.UUID, intake_item_id: uuid.UUID) -> ExternalIngestResult:
        return self.result


class _ListCollections:
    async def list(self, session, *, user_id: uuid.UUID, limit: int, offset: int, workspace_id: uuid.UUID | None) -> CollectionListResponse:
        now = datetime.now(UTC)
        item = CollectionResponse(
            id=uuid.uuid4(),
            user_id=user_id,
            name="Inbox",
            description=None,
            color=None,
            workspace_id=None,
            access_role="owner",
            created_at=now,
            updated_at=None,
        )
        return CollectionListResponse(items=[item], total=1, limit=limit, offset=offset)


class _QueryExecutor:
    def __init__(self) -> None:
        self.received: QueryPayload | None = None

    async def __call__(self, dto: QueryPayload) -> QueryResult:
        self.received = dto
        return QueryResult(
            conversation_id=uuid.uuid4(),
            query=dto.query,
            answer="Saved answer",
            sources=[],
            refrag_context=RefragContextPackage(
                query=dto.query,
                full_text_chunks=[],
                compressed_chunks=[],
                discarded_chunks=[],
                total_original_tokens=0,
                total_context_tokens=0,
                compression_strategy="none",
            ),
            debug=None,
        )


def test_webhook_ingest_authenticates_api_key_and_forwards_tags() -> None:
    user_id = uuid.uuid4()
    api_key_id = uuid.uuid4()
    document_id = uuid.uuid4()
    authenticate = _AuthenticateApiKey(user_id, api_key_id)
    ingest = _IngestExternalItem(_external_result(user_id=user_id, api_key_id=api_key_id, document_id=document_id))
    client = _client({ApiKeyAuthenticator: authenticate, ExternalItemIngester: ingest})

    try:
        response = client.post(
            "/api/v1/webhooks/ingest",
            headers={"Authorization": "Bearer ctx_test"},
            json={
                "title": "Webhook note",
                "type": "MARKDOWN",
                "raw_content": "# Note",
                "tags": ["notion", "research"],
                "provider": "n8n",
                "external_id": "run-1",
            },
        )
    finally:
        client.close()

    assert response.status_code == 202
    assert response.json()["intake_item"]["status"] == "QUEUED"
    assert authenticate.received == ("Bearer ctx_test", "ingest:write")
    assert ingest.received is not None
    assert ingest.received["user_id"] == user_id
    assert ingest.received["api_key_id"] == api_key_id
    assert ingest.received["tags"] == ["notion", "research"]
    assert ingest.received["provider"] == "n8n"


def test_public_api_ingest_defaults_provider() -> None:
    user_id = uuid.uuid4()
    api_key_id = uuid.uuid4()
    document_id = uuid.uuid4()
    authenticate = _AuthenticateApiKey(user_id, api_key_id)
    ingest = _IngestExternalItem(_external_result(user_id=user_id, api_key_id=api_key_id, document_id=document_id))
    client = _client({ApiKeyAuthenticator: authenticate, ExternalItemIngester: ingest})

    try:
        response = client.post(
            "/api/v1/public-api/ingest",
            headers={"Authorization": "Bearer ctx_test"},
            json={
                "title": "Saved article",
                "type": "URL",
                "source_url": "https://example.com",
            },
        )
    finally:
        client.close()

    assert response.status_code == 202
    assert ingest.received is not None
    assert ingest.received["provider"] == "public-api"
    assert ingest.received["source_url"] == "https://example.com"


def test_public_api_intake_status_list_and_retry_use_scoped_auth() -> None:
    user_id = uuid.uuid4()
    api_key_id = uuid.uuid4()
    document_id = uuid.uuid4()
    result = _external_result(user_id=user_id, api_key_id=api_key_id, document_id=document_id)
    authenticate = _AuthenticateApiKey(user_id, api_key_id)
    intake_service = _ExternalIntakeService(result.intake_item, result)
    client = _client(
        {
            ApiKeyAuthenticator: authenticate,
            ExternalIntakeService: intake_service,
        }
    )

    try:
        list_response = client.get("/api/v1/public-api/intake", headers={"Authorization": "Bearer ctx_test"})
        get_response = client.get(f"/api/v1/public-api/intake/{result.intake_item.id}", headers={"Authorization": "Bearer ctx_test"})
        retry_response = client.post(
            f"/api/v1/public-api/intake/{result.intake_item.id}/retry",
            headers={"Authorization": "Bearer ctx_test"},
        )
    finally:
        client.close()

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == str(result.intake_item.id)
    assert get_response.status_code == 200
    assert retry_response.status_code == 202
    assert retry_response.json()["intake_item"]["document_id"] == str(document_id)


def test_public_api_collections_and_query_use_scoped_auth() -> None:
    user_id = uuid.uuid4()
    api_key_id = uuid.uuid4()
    authenticate = _AuthenticateApiKey(user_id, api_key_id)
    query = _QueryExecutor()
    client = _client(
        {
            ApiKeyAuthenticator: authenticate,
            CollectionService: _ListCollections(),
            QueryExecutor: query,
        }
    )

    try:
        collections_response = client.get("/api/v1/public-api/collections", headers={"Authorization": "Bearer ctx_test"})
        query_response = client.post(
            "/api/v1/public-api/query",
            headers={"Authorization": "Bearer ctx_test"},
            json={"query": "What did I save?"},
        )
    finally:
        client.close()

    assert collections_response.status_code == 200
    assert collections_response.json()["items"][0]["name"] == "Inbox"
    assert query_response.status_code == 200
    assert query_response.json()["answer"] == "Saved answer"
    assert query.received is not None
    assert query.received.user_id == user_id


def _client(dependencies: Mapping[type[object], object]) -> TestClient:
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer(dependencies)._dependencies)
    return TestClient(app, raise_server_exceptions=False)


def _external_result(*, user_id: uuid.UUID, api_key_id: uuid.UUID, document_id: uuid.UUID) -> ExternalIngestResult:
    now = datetime.now(UTC)
    intake_item = ExternalIntakeItem(
        id=uuid.uuid4(),
        user_id=user_id,
        api_key_id=api_key_id,
        provider="webhook",
        external_id="run-1",
        idempotency_key="run-1",
        title="Webhook note",
        type=DocumentType.MARKDOWN,
        collection_id=None,
        tags=["notion"],
        source_url=None,
        status="QUEUED",
        error_reason=None,
        document_id=document_id,
        payload_metadata={},
        created_at=now,
        updated_at=None,
    )
    document = DocumentResult(
        id=document_id,
        user_id=user_id,
        collection_id=None,
        title="Webhook note",
        type=DocumentType.MARKDOWN,
        status=DocumentStatus.QUEUED,
        source_url=None,
        file_path=None,
        file_size_bytes=None,
        raw_content="# Note",
        summary=None,
        word_count=1,
        language=None,
        entities=None,
        categories=None,
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=now,
        updated_at=None,
        tags=["notion"],
    )
    return ExternalIngestResult(intake_item=intake_item, document=document)
