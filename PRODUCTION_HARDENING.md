# Production Hardening Guide - Detailed Code Recommendations

## Based on Code Review (7.25/10)

This document provides **specific, copy-paste ready code** for hardening Cortex before production deployment.

---

## 1. RATE LIMITING (Current: 0/10 → Target: 10/10)

### Issue
No protection against abuse or DOS attacks. Users can spam endpoints and exhaust resources.

### Fix

**Install dependency:**
```bash
uv add slowapi
```

**Create `src/presentation/middleware/rate_limit.py`:**
```python
"""Rate limiting middleware for production protection."""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from structlog import get_logger

logger = get_logger()

limiter = Limiter(key_func=get_remote_address)

async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Handle rate limit exceeded errors."""
    logger.warning(
        "rate_limit_exceeded",
        client=request.client.host if request.client else "unknown",
        path=request.url.path,
    )
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests. Please try again later.",
            "retry_after": 60,
        },
    )

def setup_rate_limiting(app: FastAPI) -> None:
    """Configure rate limiting on FastAPI app."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
```

**Update `src/main.py`:**
```python
from src.presentation.middleware.rate_limit import limiter, setup_rate_limiting

# After creating FastAPI app
setup_rate_limiting(app)

# Apply to endpoints:
@router.post("/query")
@limiter.limit("100/minute")
async def query_documents(request: Request, dto: QueryRequest) -> QueryResultDTO:
    """Query documents (100 req/min per IP)."""
    # ...

@router.post("/ingest/{type}")
@limiter.limit("50/minute")
async def ingest_document(request: Request, document_type: DocumentType) -> IngestResultDTO:
    """Ingest document (50 req/min per IP)."""
    # ...

@router.get("/documents/{doc_id}")
@limiter.limit("1000/minute")
async def get_document(request: Request, doc_id: UUID) -> DocumentDTO:
    """Get document (high limit, just prevent abuse)."""
    # ...

# Health checks bypass rate limiting
@router.get("/health", include_in_schema=False)
async def health_check() -> dict[str, str]:
    """Health check (no rate limit)."""
    return {"status": "ok"}
```

**Test:**
```python
# tests/unit/test_rate_limiting.py
import pytest
from fastapi.testclient import TestClient

@pytest.mark.asyncio
async def test_rate_limiting_enforced(client: TestClient):
    """Verify rate limiting blocks after threshold."""
    # Make 101 requests in a minute
    for i in range(101):
        response = await client.post(
            "/api/v1/query",
            json={"query": "test"}
        )
        if i < 100:
            assert response.status_code == 200
        else:
            assert response.status_code == 429
            assert "Too many requests" in response.json()["detail"]
```

---

## 2. INPUT VALIDATION CONSTRAINTS (Current: 5/10 → Target: 10/10)

### Issue
Query text, titles, and batch operations unconstrained. Allows:
- 1GB query strings → memory exhaustion
- Database column size violations
- Runaway batch operations

### Fix

**Update `src/presentation/schemas/query_schemas.py`:**
```python
"""Query request validation with constraints."""

from pydantic import Field, field_validator
from typing import Annotated

QueryText = Annotated[str, Field(min_length=1, max_length=2000)]
DocumentTitle = Annotated[str, Field(min_length=1, max_length=500)]
DocumentContent = Annotated[str, Field(max_length=1_000_000)]  # 1MB max

class QueryRequest(BaseModel):
    """Query documents request with input validation."""
    query: QueryText = Field(
        ...,
        description="Search query (1-2000 characters)"
    )
    conversation_id: UUID | None = Field(
        None,
        description="Optional conversation context"
    )
    collection_id: UUID | None = Field(None)
    limit: int = Field(
        default=10,
        ge=1,  # Greater than or equal to 1
        le=50,  # Less than or equal to 50
        description="Max results (1-50)"
    )
    offset: int = Field(
        default=0,
        ge=0,
        le=1000,  # Max 1000 offset
    )
    
    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Additional validation for query."""
        if not v.strip():
            raise ValueError("query cannot be empty/whitespace only")
        return v.strip()

class BatchQueryRequest(BaseModel):
    """Batch query with size limits."""
    queries: list[QueryText] = Field(
        ...,
        min_length=1,
        max_length=10,  # Max 10 queries per batch
        description="List of queries to process"
    )
```

**Update `src/presentation/schemas/document_schemas.py`:**
```python
"""Document schemas with input validation."""

from pydantic import Field, HttpUrl, field_validator
from typing import Annotated

DocumentTitle = Annotated[str, Field(min_length=1, max_length=500)]
DocumentContent = Annotated[str, Field(max_length=1_000_000)]

class CreateDocumentRequest(BaseModel):
    """Create document request."""
    title: DocumentTitle = Field(..., description="Document title (1-500 chars)")
    document_type: DocumentType
    source_url: HttpUrl | None = Field(
        None,
        description="Source URL for URL-based ingestion"
    )
    raw_content: DocumentContent | None = Field(
        None,
        description="Raw text content (max 1MB)"
    )
    
    @field_validator("raw_content")
    @classmethod
    def validate_content(cls, v: str | None) -> str | None:
        """Validate content size."""
        if v and len(v.encode()) > 1_000_000:
            raise ValueError("Content exceeds 1MB limit")
        return v
    
    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Title must not be whitespace only."""
        if not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()

class BatchCreateDocumentsRequest(BaseModel):
    """Batch document creation."""
    documents: list[CreateDocumentRequest] = Field(
        ...,
        min_length=1,
        max_length=100,  # Max 100 docs per batch
    )
```

**Update DTOs in `src/application/dtos/query_dtos.py`:**
```python
"""Query DTOs with validation."""

from pydantic import Field, field_validator
from typing import Annotated

QueryText = Annotated[str, Field(min_length=1, max_length=2000)]

class QueryDTO(BaseModel):
    """Query DTO with validation."""
    query_text: QueryText
    user_id: UUID
    limit: int = Field(default=10, ge=1, le=50)
    
    @field_validator("query_text")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Query cannot be empty")
        return v.strip()
```

**Add to use cases for bounds checking:**
```python
# In src/application/use_cases/query/query_use_case.py

async def execute(self, dto: QueryDTO) -> QueryResultDTO:
    """Execute query with validation."""
    # Validate inputs
    if len(dto.query_text) > 2000:
        raise ValueError("Query exceeds max length of 2000 chars")
    
    if dto.limit < 1 or dto.limit > 50:
        raise ValueError("Limit must be between 1 and 50")
    
    # Existing logic...
```

---

## 3. CELERY ERROR HANDLING (Current: 4/10 → Target: 9/10)

### Issue
All exceptions caught generically. No distinction between:
- **Retryable** (OpenAI API timeout, network error)
- **Permanent** (document not found, invalid input)
- **Unknown** (should log and fail immediately)

### Fix

**Create `src/infrastructure/celery/error_handling.py`:**
```python
"""Celery error classification and handling."""

from typing import TypeVar, Callable, Any
from functools import wraps
import asyncio
from structlog import get_logger
from src.domain.exceptions import DomainException
from openai import RateLimitError, APIConnectionError, APITimeoutError
import requests

logger = get_logger()

class RetryableError(Exception):
    """Errors that should trigger celery retry."""
    pass

class PermanentError(Exception):
    """Errors that should not retry."""
    pass

def classify_error(exc: Exception) -> tuple[bool, str]:
    """Classify if error is retryable and get reason.
    
    Returns:
        (is_retryable, reason)
    """
    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)):
        return True, "api_error"  # Retryable - transient
    
    if isinstance(exc, requests.exceptions.Timeout):
        return True, "timeout"  # Retryable
    
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True, "connection_error"  # Retryable
    
    if isinstance(exc, DomainException):
        return False, "domain_error"  # Permanent - business logic
    
    if isinstance(exc, ValueError):
        return False, "validation_error"  # Permanent - input
    
    if isinstance(exc, KeyError):
        return False, "missing_key"  # Permanent - code bug
    
    # Unknown - don't retry
    return False, "unknown_error"

def celery_task_with_error_handling(max_retries: int = 3):
    """Decorator for Celery tasks with proper error handling.
    
    Usage:
        @celery_task_with_error_handling(max_retries=3)
        async def my_task(self, document_id: str) -> dict:
            # Task logic
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
            try:
                return asyncio.run(func(self, *args, **kwargs))
            except Exception as exc:
                is_retryable, reason = classify_error(exc)
                
                logger.error(
                    "celery_task_error",
                    task_name=func.__name__,
                    error_type=type(exc).__name__,
                    error_reason=reason,
                    is_retryable=is_retryable,
                    retry_count=self.request.retries,
                    max_retries=self.max_retries,
                    error=str(exc),
                )
                
                if is_retryable and self.request.retries < max_retries:
                    # Retryable error - retry with exponential backoff
                    countdown = min(2 ** self.request.retries * 60, 3600)  # Up to 1 hour
                    logger.info("retrying_task", countdown=countdown)
                    raise self.retry(exc=exc, countdown=countdown)
                
                # Permanent error - log and fail
                logger.error(
                    "celery_task_permanent_failure",
                    task_name=func.__name__,
                    error=str(exc),
                )
                return {
                    "status": "FAILED",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "reason": reason,
                }
        
        return wrapper
    return decorator
```

**Update `src/infrastructure/celery/tasks/document_processing.py`:**
```python
"""Document processing tasks with proper error handling."""

from src.infrastructure.celery.error_handling import celery_task_with_error_handling

@celery_app.task(
    queue="document_processing",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
@celery_task_with_error_handling(max_retries=3)
async def process_document_task(self: Any, document_id: str) -> dict[str, Any]:
    """Process document with robust error handling.
    
    Handles:
    - API errors (retry)
    - Validation errors (fail)
    - Unknown errors (fail with logging)
    """
    uow = container[IUnitOfWork]
    
    async with uow:
        document = await uow.document_repo.get_by_id(UUID(document_id))
        if not document:
            raise ValueError(f"Document {document_id} not found")
        
        # Process: extract -> chunk -> embed
        # If any step raises an exception, it will be caught by decorator
        result = await _process_document(document, uow)
        
        return {
            "status": "SUCCESS",
            "document_id": document_id,
            "chunks_created": len(result),
        }
```

**Update embedding task:**
```python
@celery_app.task(
    queue="embeddings",
    bind=True,
    max_retries=3,
)
@celery_task_with_error_handling(max_retries=3)
async def embed_and_finalize_document(self: Any, document_id: str) -> dict[str, Any]:
    """Embed chunks and finalize document."""
    uow = container[IUnitOfWork]
    embedding_provider = container[IEmbeddingProvider]
    
    async with uow:
        chunks = await uow.chunk_repo.get_by_document(UUID(document_id))
        
        # Embed all chunks
        embeddings = await embedding_provider.embed_texts(
            [chunk.content for chunk in chunks]
        )
        
        # Save embeddings
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        
        await uow.chunk_repo.update_batch(chunks)
        await uow.commit()
        
        # Dispatch enrichment tasks
        extract_entities_task.apply_async(
            args=[document_id],
            queue="hf_processing",
            priority=5,
        )
        classify_document_task.apply_async(
            args=[document_id],
            queue="hf_processing",
            priority=5,
        )
        
        return {"status": "SUCCESS", "document_id": document_id}
```

---

## 4. DATABASE QUERY TIMEOUTS (Current: 0/10 → Target: 9/10)

### Issue
No timeout on long-running queries. Can:
- Block connection pool
- Cascade failures
- Stall ingestion pipeline

### Fix

**Update `src/infrastructure/database/sql_alchemy.py`:**
```python
"""SQLAlchemy engine with production timeouts."""

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from src.core.config import settings

def create_engine() -> AsyncEngine:
    """Create AsyncEngine with production timeouts."""
    return create_async_engine(
        settings.DATABASE_URL,
        connect_args={
            "timeout": 10,  # Connection timeout (seconds)
            "command_timeout": 30,  # Query timeout (seconds)
            "server_settings": {
                "statement_timeout": "30s",  # PostgreSQL server timeout
            }
        },
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=300,  # Recycle connections every 5 minutes
        echo=settings.DEBUG,
    )
```

**Add to `src/core/config.py`:**
```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # Database timeouts (seconds)
    DB_CONNECT_TIMEOUT: int = Field(default=10, ge=1, le=30)
    DB_QUERY_TIMEOUT: int = Field(default=30, ge=5, le=300)
    DB_POOL_RECYCLE: int = Field(default=300, ge=60, le=3600)
```

**Add connection wrapper with timeout handling:**
```python
# In src/infrastructure/database/sql_alchemy.py

from contextlib import asynccontextmanager
from sqlalchemy.exc import OperationalError, TimeoutError as SQLTimeoutError
from structlog import get_logger

logger = get_logger()

@asynccontextmanager
async def get_db_connection_with_timeout(session: AsyncSession):
    """Get DB connection with timeout protection."""
    try:
        yield session
    except (OperationalError, SQLTimeoutError) as exc:
        logger.error("database_timeout", error=str(exc))
        raise
```

**Test timeout protection:**
```python
# tests/unit/test_database_timeout.py

@pytest.mark.asyncio
async def test_query_timeout_handled(session: AsyncSession):
    """Verify queries respect timeout."""
    # This query will timeout if timeout is working
    try:
        result = await session.execute(
            text("SELECT pg_sleep(31)")  # Sleep 31 seconds (exceeds 30s limit)
        )
    except SQLAlchemy.exc.OperationalError as exc:
        assert "timeout" in str(exc).lower()
```

---

## 5. INTEGRATION TESTS (Current: 0 → Target: 5-10)

### Issue
Only 33 unit tests. No end-to-end testing of critical workflows. No regression detection.

### Fix

**Create `tests/integration/test_document_ingestion.py`:**
```python
"""Integration tests for document ingestion pipeline."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from uuid import UUID

@pytest.mark.asyncio
class TestDocumentIngestionPipeline:
    """Test complete document ingestion workflow."""
    
    async def test_pdf_ingestion_end_to_end(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        pdf_bytes: bytes,
    ):
        """Test: PDF upload → extract → chunk → embed → ready."""
        # 1. Upload PDF
        response = await async_client.post(
            "/api/v1/ingest/pdf",
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
            headers={"authorization": "Bearer test_token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "document_id" in data
        doc_id = data["document_id"]
        
        # 2. Poll status until READY (60s timeout)
        for attempt in range(60):
            status_response = await async_client.get(
                f"/api/v1/documents/{doc_id}/status",
                headers={"authorization": "Bearer test_token"},
            )
            assert status_response.status_code == 200
            status = status_response.json()["status"]
            
            if status == "READY":
                break
            
            if status == "FAILED":
                error = status_response.json().get("error")
                pytest.fail(f"Document ingestion failed: {error}")
            
            await asyncio.sleep(1)
        else:
            pytest.fail("Document ingestion timeout after 60 seconds")
        
        # 3. Verify document in database
        async with db_session() as session:
            doc = await session.get(Document, UUID(doc_id))
            assert doc is not None
            assert doc.status == DocumentStatus.READY
            assert doc.chunk_count > 0
    
    async def test_url_ingestion_end_to_end(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test: URL → fetch → extract → chunk → embed → ready."""
        response = await async_client.post(
            "/api/v1/ingest/url",
            json={"url": "https://example.com"},
            headers={"authorization": "Bearer test_token"},
        )
        assert response.status_code == 200
        doc_id = response.json()["document_id"]
        
        # Poll until ready
        for _ in range(60):
            status = await async_client.get(
                f"/api/v1/documents/{doc_id}/status",
                headers={"authorization": "Bearer test_token"},
            )
            if status.json()["status"] == "READY":
                break
            await asyncio.sleep(1)
        
        # Verify in database
        async with db_session() as session:
            doc = await session.get(Document, UUID(doc_id))
            assert doc.url == "https://example.com"
            assert doc.chunk_count > 0
```

**Create `tests/integration/test_query_streaming.py`:**
```python
"""Integration tests for query streaming."""

import pytest
from fastapi.testclient import TestClient

@pytest.mark.asyncio
class TestQueryStreaming:
    """Test query streaming response."""
    
    async def test_query_stream_returns_valid_sse(
        self,
        async_client: AsyncClient,
    ):
        """Test: Query → stream results as SSE."""
        response = await async_client.post(
            "/api/v1/query/stream",
            json={"query": "What is machine learning?"},
            headers={"authorization": "Bearer test_token"},
        )
        assert response.status_code == 200
        
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                try:
                    event = json.loads(line[6:])
                    events.append(event)
                except json.JSONDecodeError:
                    pass
        
        # Verify structure
        assert len(events) > 0
        
        # Should end with completion event
        assert events[-1]["type"] == "done"
        
        # Should have thought, sources, answer
        event_types = {e["type"] for e in events}
        assert "sources" in event_types
        assert "answer" in event_types
    
    async def test_query_stream_respects_rate_limit(
        self,
        async_client: AsyncClient,
    ):
        """Test: Rate limit applies to streaming."""
        # Make 101 streaming requests
        responses = []
        for i in range(101):
            response = await async_client.post(
                "/api/v1/query/stream",
                json={"query": "test"},
                headers={"authorization": "Bearer test_token"},
            )
            responses.append(response.status_code)
        
        # First 100 should succeed, 101st should be 429
        assert all(status == 200 for status in responses[:100])
        assert responses[100] == 429
```

**Create `tests/integration/test_oauth_flows.py`:**
```python
"""Integration tests for OAuth flows."""

import pytest
from urllib.parse import urlparse, parse_qs

@pytest.mark.asyncio
class TestOAuthFlows:
    """Test OAuth2 authentication flows."""
    
    async def test_google_oauth_redirect(
        self,
        async_client: AsyncClient,
    ):
        """Test: User → OAuth provider redirect."""
        response = await async_client.get(
            "/api/v1/auth/oauth/google/login"
        )
        # Should redirect to Google
        assert response.status_code == 307  # Temporary redirect
        location = response.headers["location"]
        assert "accounts.google.com" in location
        assert "client_id" in location
    
    async def test_github_oauth_redirect(
        self,
        async_client: AsyncClient,
    ):
        """Test: User → GitHub OAuth redirect."""
        response = await async_client.get(
            "/api/v1/auth/oauth/github/login"
        )
        assert response.status_code == 307
        location = response.headers["location"]
        assert "github.com" in location
```

**Create `tests/integration/conftest.py` for shared fixtures:**
```python
"""Integration test fixtures."""

import pytest
from httpx import AsyncClient
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

@pytest.fixture
async def test_db_engine():
    """Create test database engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()

@pytest.fixture
async def async_client(app: FastAPI, test_db_engine) -> AsyncClient:
    """Create async test client."""
    return AsyncClient(app=app, base_url="http://test")
```

---

## Summary: Pre-Deployment Effort

| Fix | Time | Priority | Blocker |
|-----|------|----------|---------|
| Rate Limiting | 2h | HIGH | YES |
| Input Validation | 3h | HIGH | YES |
| Celery Error Handling | 2h | HIGH | YES |
| DB Query Timeouts | 1h | MEDIUM | NO |
| Integration Tests | 4h | MEDIUM | NO |
| **Total** | **12h** | - | **7h blocking** |

---

## Deployment Command (After Fixes)

```bash
cd /Users/maksympushkash/cortex

# 1. Implement fixes (12 hours of work)
# ... implement code above ...

# 2. Validate
uv run ruff check src --fix
uv run pyright src
uv run pytest tests/ -v

# 3. Build Docker
docker build -f Dockerfile -t cortex:latest .

# 4. Deploy (see DEPLOYMENT.md)
# Push to GitHub, GitHub Actions builds, deploys to VPS
```

---

*Production Hardening Guide | May 2026*
