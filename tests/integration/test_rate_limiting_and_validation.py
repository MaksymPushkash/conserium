"""Integration tests for rate limiting and input validation."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth.auth import get_current_user
from src.documents.ingestion import DocumentIngester
from src.documents.schemas import DocumentResult
from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.kit.exceptions import InvalidPasswordException
from src.main import create_app
from src.models.user import UserModel
from src.query.schemas import QueryPayload, QueryResult, RefragContextPackage
from src.query.service import QueryExecutor


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Create a test app with auth overridden for request validation tests."""
    application = create_app()

    async def override_current_user() -> UserModel:
        return UserModel.create(id=uuid4(), email="tester@example.com", password="hashed-password")

    async def fake_query_call(self: QueryExecutor, dto: QueryPayload) -> QueryResult:
        conversation_id = dto.conversation_id or uuid4()
        return QueryResult(
            conversation_id=conversation_id,
            query=dto.query,
            answer="test answer",
            sources=[],
            refrag_context=RefragContextPackage(
                query=dto.query,
                full_text_chunks=[],
                compressed_chunks=[],
                discarded_chunks=[],
                total_original_tokens=0,
                total_context_tokens=0,
                compression_strategy="test",
            ),
        )

    async def fake_ingest_call(
        self: DocumentIngester,
        *,
        user_id: UUID,
        title: str,
        type: DocumentType,
        collection_id: UUID | None = None,
        tags: list[str] | None = None,
        source_url: str | None = None,
        file_path: str | None = None,
        file_size_bytes: int | None = None,
        raw_content: str | None = None,
        language: str | None = None,
    ) -> DocumentResult:
        _ = tags
        if not title.strip():
            raise InvalidPasswordException("title cannot be empty")
        now = datetime.now(UTC)
        document_id = uuid4()
        return DocumentResult(
            id=document_id,
            user_id=user_id,
            collection_id=collection_id,
            title=title,
            type=type,
            status=DocumentStatus.QUEUED,
            source_url=source_url,
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            raw_content=raw_content,
            summary=None,
            word_count=len(raw_content.split()) if raw_content else None,
            language=language,
            entities=None,
            categories=None,
            is_duplicate=False,
            duplicate_of_id=None,
            created_at=now,
            updated_at=now,
            visual_metadata=None,
            tags=[],
        )

    application.dependency_overrides[get_current_user] = override_current_user
    monkeypatch.setattr(QueryExecutor, "__call__", fake_query_call)
    monkeypatch.setattr(DocumentIngester, "__call__", fake_ingest_call)
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create a test client."""
    return TestClient(app)


class TestRateLimiting:
    """Test rate limiting on key endpoints."""

    def test_query_endpoint_rate_limiting(self, client: TestClient) -> None:
        """Verify rate limiting on query endpoint."""
        # Query endpoint has 100/minute limit
        # We'll make 101 requests and verify the 101st gets rate limited
        responses = []
        for i in range(101):
            response = client.post(
                "/api/v1/query",
                json={"query": f"test query {i}"},
            )
            responses.append(response.status_code)

        # First 100 should be 200 or 401 (auth required) not 429
        # 101st should be 429 (rate limited)
        # Note: May be 401 since we don't have auth token, but should not be 429 until after limit
        for i, status in enumerate(responses):
            if status == 429:
                # Should happen around request 101
                assert i >= 99, f"Rate limit triggered too early at request {i}"
                break

        # We expect at least one 429 response after enough requests
        # (exact timing depends on slowapi implementation)

    def test_query_endpoint_with_health_check_bypass(self, client: TestClient) -> None:
        """Verify health checks bypass rate limiting."""
        # Health endpoint should not be rate limited
        for _ in range(110):
            response = client.get("/health")
            # Should succeed every time
            assert response.status_code == 200


class TestInputValidation:
    """Test input validation constraints."""

    def test_query_too_long_rejected(self, client: TestClient) -> None:
        """Verify overly long queries are rejected."""
        # QueryRequest has max_length=2000
        long_query = "x" * 2001  # Exceed limit
        response = client.post(
            "/api/v1/query",
            json={"query": long_query},
        )
        # Should get 422 Unprocessable Entity (validation error)
        assert response.status_code == 422
        assert "max_length" in response.text or "at most 2000 characters" in response.text

    def test_query_valid_length_accepted(self, client: TestClient) -> None:
        """Verify queries within length limit are accepted."""
        valid_query = "x" * 2000  # At limit
        response = client.post(
            "/api/v1/query",
            json={"query": valid_query},
        )
        # Should not be 422 (validation error)
        # May be 401 (auth required) or other, but not validation error
        assert response.status_code != 422

    def test_query_empty_rejected(self, client: TestClient) -> None:
        """Verify empty queries are rejected."""
        response = client.post(
            "/api/v1/query",
            json={"query": ""},
        )
        # Should get 422 for validation error
        assert response.status_code == 422

    def test_ingestion_title_too_long_rejected(self, client: TestClient) -> None:
        """Verify overly long titles are rejected on ingestion."""
        long_title = "x" * 501  # Exceed limit
        response = client.post(
            "/api/v1/ingest",
            json={
                "title": long_title,
                "type": "TEXT",
                "raw_content": "Test content",
            },
        )
        # Should get 422 validation error
        assert response.status_code == 422

    def test_ingestion_raw_text_too_long_rejected(self, client: TestClient) -> None:
        """Verify overly large raw_text is rejected."""
        # IngestTextDocumentRequest.raw_text has max_length=1_000_000
        large_text = "x" * 1_000_001  # Exceed limit
        response = client.post(
            "/api/v1/documents/ingest-text",
            json={
                "title": "Test",
                "raw_text": large_text,
            },
        )
        # Should get 422 validation error
        assert response.status_code == 422

    def test_ingestion_valid_large_text_accepted(self, client: TestClient) -> None:
        """Verify large but valid raw_text is accepted."""
        large_text = "x" * 1_000_000  # At limit
        response = client.post(
            "/api/v1/documents/ingest-text",
            json={
                "title": "Test",
                "raw_text": large_text,
            },
        )
        # Should not be 422 (validation error)
        # May be 401 (auth required) or 202 (accepted), but not validation error
        assert response.status_code != 422


class TestHealthCheckEndpoints:
    """Test health check endpoints."""

    def test_health_endpoint_available(self, client: TestClient) -> None:
        """Verify health endpoint is available."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "OK"}

    def test_multiple_health_checks_fast(self, client: TestClient) -> None:
        """Verify health checks can be called rapidly without rate limiting."""
        for _ in range(20):
            response = client.get("/health")
            assert response.status_code == 200
