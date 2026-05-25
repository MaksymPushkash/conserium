import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from src.application.dtos.api_key_dtos import ApiKeyPrincipalDTO
from src.application.dtos.document_dtos import DocumentDTO
from src.application.dtos.external_intake_dtos import ExternalIngestResultDTO, ExternalIntakeItemDTO
from src.application.use_cases.api_keys import AuthenticateApiKeyUseCase
from src.application.use_cases.external_intake import IngestExternalItemUseCase
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType
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


class _AuthenticateApiKey:
    def __init__(self, user_id: uuid.UUID, api_key_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.api_key_id = api_key_id
        self.received: tuple[str, str] | None = None

    async def __call__(self, token: str, *, required_scope: str) -> ApiKeyPrincipalDTO:
        self.received = (token, required_scope)
        return ApiKeyPrincipalDTO(user_id=self.user_id, api_key_id=self.api_key_id, scopes=[required_scope])


class _IngestExternalItem:
    def __init__(self, result: ExternalIngestResultDTO) -> None:
        self.result = result
        self.received = None

    async def __call__(self, dto):
        self.received = dto
        return self.result


def test_webhook_ingest_authenticates_api_key_and_forwards_tags() -> None:
    user_id = uuid.uuid4()
    api_key_id = uuid.uuid4()
    document_id = uuid.uuid4()
    authenticate = _AuthenticateApiKey(user_id, api_key_id)
    ingest = _IngestExternalItem(_external_result(user_id=user_id, api_key_id=api_key_id, document_id=document_id))
    client = _client({AuthenticateApiKeyUseCase: authenticate, IngestExternalItemUseCase: ingest})

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
    assert ingest.received.user_id == user_id
    assert ingest.received.api_key_id == api_key_id
    assert ingest.received.tags == ["notion", "research"]
    assert ingest.received.provider == "n8n"


def test_public_api_ingest_defaults_provider() -> None:
    user_id = uuid.uuid4()
    api_key_id = uuid.uuid4()
    document_id = uuid.uuid4()
    authenticate = _AuthenticateApiKey(user_id, api_key_id)
    ingest = _IngestExternalItem(_external_result(user_id=user_id, api_key_id=api_key_id, document_id=document_id))
    client = _client({AuthenticateApiKeyUseCase: authenticate, IngestExternalItemUseCase: ingest})

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
    assert ingest.received.provider == "public-api"
    assert ingest.received.source_url == "https://example.com"


def _client(dependencies: Mapping[type[object], object]) -> TestClient:
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(dependencies)
    return TestClient(app, raise_server_exceptions=False)


def _external_result(*, user_id: uuid.UUID, api_key_id: uuid.UUID, document_id: uuid.UUID) -> ExternalIngestResultDTO:
    now = datetime.now(UTC)
    intake_item = ExternalIntakeItemDTO(
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
    document = DocumentDTO(
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
    return ExternalIngestResultDTO(intake_item=intake_item, document=document)
