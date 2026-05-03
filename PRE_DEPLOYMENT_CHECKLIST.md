# Pre-Deployment Hardening Checklist

## Critical Fixes (Must Complete Before VPS Deployment)

### 1. Rate Limiting ✅ REQUIRED
**Severity:** HIGH - Protects against abuse
**Effort:** 2 hours
**Status:** Not yet implemented

```bash
# Install
uv add slowapi

# Add to src/presentation/middleware/rate_limit.py and main.py
# Then: @limiter.limit("100/minute") on /query endpoint
```

**Why:** Without this, malicious users can:
- DOS your API by spamming requests
- Run up your OpenAI bill with bot queries
- Exhaust database connections

---

### 2. Input Validation Constraints ✅ REQUIRED
**Severity:** HIGH - Prevents resource exhaustion
**Effort:** 3 hours
**Status:** Partially done (schemas exist, max_length missing)

```bash
# Update src/presentation/schemas/*.py:
# QueryRequest.query: max_length=2000
# CreateDocumentDTO.title: max_length=500
# QueryRequest.limit: max=50
```

**Why:** Without this:
- User can send 1GB query string → memory exhaustion
- Large payloads block workers
- Unbounded batch operations

---

### 3. Celery Error Handling ✅ REQUIRED
**Severity:** HIGH - Production stability
**Effort:** 2 hours
**Status:** Generic exceptions being caught

```bash
# Update src/infrastructure/celery/tasks/*.py:
# Separate retryable (OpenAIError, RequestException) 
# from permanent (DocumentNotFoundException, ValueError)
# from unknown (catch all with logging)
```

**Why:** Without this:
- Permanent failures retry forever (wastes resources)
- No distinction between API failures and logic bugs
- Silent failures in dead-letter queue

---

### 4. Database Query Timeouts ✅ RECOMMENDED
**Severity:** MEDIUM - Prevents resource starvation
**Effort:** 1 hour
**Status:** Not configured

```bash
# Update src/infrastructure/database/sql_alchemy.py:
# Add connect_args={"command_timeout": 30}
# Add pool_recycle=300
```

**Why:** Without this:
- Slow queries block connection pool
- All subsequent requests timeout
- Cascading failure pattern

---

### 5. Integration Tests ✅ RECOMMENDED
**Severity:** MEDIUM - Confidence before production
**Effort:** 4 hours
**Status:** Only 33 tests, 0 integration tests

```bash
# Create tests/integration/test_document_pipeline.py:
# - Document ingestion E2E
# - Query with streaming
# - OAuth2 flows
# - Error scenarios
```

**Why:** Without this:
- Features break silently in production
- No regression detection
- Unknown failure modes

---

## Implementation Order (Priority)

1. **Rate Limiting** (2h) - Do first
2. **Input Validation** (3h) - Do second
3. **Celery Error Handling** (2h) - Do third
4. **Database Timeouts** (1h) - Do fourth
5. **Integration Tests** (4h) - Do after code fixes

**Total Time: ~12 hours (1-2 days)**

---

## Validation Checklist After Fixes

After implementing each fix, run:

```bash
# 1. Lint
uv run ruff check src --fix

# 2. Type check
uv run mypy src

# 3. Test
uv run pytest tests/unit -v

# 4. Integration test (if implemented)
uv run pytest tests/integration -v

# 5. Docker build
docker build -f Dockerfile .
```

---

## Post-Fixes: VPS Deployment Readiness

Once all 5 fixes complete, you're ready for VPS:

- ✅ Protected against abuse (rate limiting)
- ✅ Protected against resource exhaustion (input validation)
- ✅ Stable background processing (error handling)
- ✅ No hanging queries (timeouts)
- ✅ Confidence in critical paths (tests)

---

## Code Review Scorecard (Current: 7.25/10)

| Area | Score | After Fixes |
|------|-------|------------|
| Security | 8/10 | 9/10 (rate limit + input validation) |
| Error Handling | 6/10 | 8/10 (Celery fix) |
| Reliability | 6/10 | 8/10 (timeouts + tests) |
| Testing | 4/10 | 5/10 (integration tests) |
| **OVERALL** | **7.25/10** | **8.5/10** |

---

## What Can Deploy as-is (Post-fixes)

✅ Ready for production:
- FastAPI app with HTTPS
- PostgreSQL + migrations
- Redis caching
- Celery background jobs
- OAuth2 authentication
- Document ingestion pipeline
- LangGraph query orchestration
- Monitoring hooks

⚠️ Post-deployment (not blocking):
- Prometheus metrics endpoint
- RBAC system
- Audit logging
- Langfuse full integration
- Distributed tracing

---

## Command to Start Implementation

```bash
cd /Users/maksympushkash/cortex

# 1. Create rate limiting middleware
# 2. Update Pydantic schemas with max_length
# 3. Fix Celery error handling
# 4. Add database timeouts
# 5. Write integration tests
# 6. Run full test suite
# 7. Deploy to VPS (see DEPLOYMENT.md)
```

---

## Need Help?

Refer to:
- **DEPLOYMENT.md** - Full VPS setup guide
- **docs/project-status-and-roadmap.md** - Feature status
- Code review analysis - See session memory for full 19KB analysis

---

*Generated: May 2026 | Pre-Deployment Phase*
