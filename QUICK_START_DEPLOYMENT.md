# 🚀 Cortex: From Code Review to Production

## Complete Roadmap (Next 2 Weeks)

---

## Phase 0: Code Review Findings (Already Done ✅)

**Score: 7.25/10**

Your codebase is **production-ready** but needs **hardening** before deployment.

### Key Strengths ✅
- Clean Architecture properly implemented
- Strong security (JWT, OAuth2, SSRF protection)
- Type-safe with excellent naming
- Professional async design
- Good error handling patterns

### Critical Gaps (Blocking Production) ⚠️
1. **No rate limiting** → DOS vulnerability
2. **Input validation incomplete** → Resource exhaustion
3. **Celery errors not classified** → Cascading failures
4. **No query timeouts** → Connection pool starvation
5. **Only 33 tests** → Unknown failure modes

---

## Week 1: Pre-Deployment Hardening (7-12 hours)

### Day 1: Core Fixes (4-5 hours)

#### 1. Rate Limiting (2h)
```bash
cd /Users/maksympushkash/cortex
uv add slowapi
```
- Create `src/presentation/middleware/rate_limit.py`
- Update `src/main.py` to apply `@limiter.limit("100/minute")`
- See: `PRODUCTION_HARDENING.md` Section 1

**Status Check:**
```bash
curl -X POST http://localhost:8000/api/v1/query -d '{"query":"test"}' -H "Content-Type: application/json"
# After 100 requests: should get 429
```

#### 2. Input Validation (3h)
- Update Pydantic schemas with `max_length`, `min_length`, `ge`, `le`
- See: `PRODUCTION_HARDENING.md` Section 2

**Status Check:**
```bash
# Query too long - should fail
curl -X POST http://localhost:8000/api/v1/query \
  -d '{"query":"'$(python3 -c "print('x'*2001)")'"}'
# Should get 422 Unprocessable Entity
```

### Day 2: Error Handling & Tests (3-4 hours)

#### 3. Celery Error Handling (2h)
- Create error classification system
- Update all Celery tasks
- See: `PRODUCTION_HARDENING.md` Section 3

#### 4. Query Timeouts (1h)
- Update SQLAlchemy engine
- See: `PRODUCTION_HARDENING.md` Section 4

**Status Check:**
```bash
# Verify timeout (query will take 31s, limit is 30s)
psql -U cortex_user -d cortex_db -c "SELECT pg_sleep(31);"
# Should timeout after 30 seconds
```

### Day 3: Tests & Validation (2-3 hours)

#### 5. Integration Tests (2-3h)
- Create `tests/integration/test_document_ingestion.py`
- Create `tests/integration/test_query_streaming.py`
- Create `tests/integration/test_oauth_flows.py`
- See: `PRODUCTION_HARDENING.md` Section 5

**Status Check:**
```bash
# All tests pass
uv run pytest tests/integration -v
# Output should show 5+ passing integration tests
```

### Validation Checklist Day 3

```bash
# 1. Linting
uv run ruff check src --fix
# Should output: All checks passed

# 2. Type checking
uv run pyright src
# Should output: 0 errors, 0 warnings

# 3. All tests
uv run pytest tests/ -v --tb=short
# Should output: All passed (XX passed, X skipped)

# 4. Docker build
docker build -f Dockerfile -t cortex:v0.2.0 .
# Should complete without errors
```

---

## Week 2: VPS Deployment (3-5 days)

### Day 1: VPS Setup (3-4 hours)

1. **Provision VPS** (30min)
   - Provider: Linode, DigitalOcean, or Hetzner
   - OS: Ubuntu 22.04 LTS
   - Size: 4 CPU, 8GB RAM, 50GB SSD
   - Domain: Configure DNS A record

2. **SSH to VPS and initialize** (1h)
   ```bash
   ssh root@YOUR_VPS_IP
   # Then run initialization script from DEPLOYMENT.md Phase 1
   ```

3. **PostgreSQL & Redis** (1h)
   ```bash
   # Follow DEPLOYMENT.md Phase 1, Steps 2-3
   ```

4. **Docker & App** (1h 30min)
   ```bash
   # Follow DEPLOYMENT.md Phase 1, Step 4
   ```

### Day 2: GitHub Actions & Nginx (2-3 hours)

1. **Set GitHub Secrets** (30min)
   - Go to: Repo Settings → Secrets and variables → Actions
   - Add: `REGISTRY_TOKEN`, `VPS_SSH_KEY`, `VPS_HOST`, etc.
   - See: `DEPLOYMENT.md` Phase 2

2. **GitHub Actions Workflow** (30min)
   - Copy `.github/workflows/deploy.yml` from `DEPLOYMENT.md`
   - Commit and push to main branch

3. **Nginx + HTTPS** (1h)
   - Copy nginx config from `DEPLOYMENT.md` Phase 3
   - Set up Let's Encrypt certificate
   - Verify: `curl https://cortex.yourdomain.com/health`

### Day 3: Deployment & Verification (1-2 hours)

1. **Trigger CI/CD Pipeline**
   ```bash
   git push origin main
   # Watch: GitHub Actions → Actions tab → Deploy workflow
   ```

2. **Verify Deployment**
   ```bash
   # HTTPS working
   curl https://cortex.yourdomain.com/health
   # Should return: {"status":"ok"}
   
   # Database migrated
   curl https://cortex.yourdomain.com/health/ready
   # Should return: {"status":"ready"}
   
   # Try document ingestion
   curl -X POST https://cortex.yourdomain.com/api/v1/ingest/text \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"title":"Test","raw_content":"Hello world"}'
   ```

3. **Monitor Logs**
   ```bash
   ssh cortex@YOUR_VPS_IP
   cd /opt/cortex
   docker-compose -f docker-compose.prod.yaml logs -f app
   ```

---

## ✅ Post-Deployment Verification

Run this checklist when deployed:

```bash
# 1. HTTPS Certificate
curl -I https://cortex.yourdomain.com
# Should show: HTTP/2 200, SSL certificate ✓

# 2. Health Checks
curl https://cortex.yourdomain.com/health
curl https://cortex.yourdomain.com/health/live
curl https://cortex.yourdomain.com/health/ready
# All should return 200

# 3. Rate Limiting Works
for i in {1..101}; do
  curl -s https://cortex.yourdomain.com/api/v1/query \
    -X POST -H "Content-Type: application/json" \
    -d '{"query":"test"}' -o /dev/null -w "%{http_code}\n"
done | grep 429 && echo "✓ Rate limiting works"

# 4. OAuth Flows
curl -I "https://cortex.yourdomain.com/api/v1/auth/oauth/google/login"
# Should return: 307 Temporary Redirect

# 5. Document Ingestion
curl -X POST "https://cortex.yourdomain.com/api/v1/ingest/text" \
  -H "Authorization: Bearer TEST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Document",
    "raw_content": "This is a test document for the production deployment."
  }'
# Should return: 200 with document_id

# 6. Query Endpoint
curl -X POST "https://cortex.yourdomain.com/api/v1/query" \
  -H "Authorization: Bearer TEST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the test document about?"}'
# Should return: 200 with query results

# 7. Celery Workers Active
ssh cortex@YOUR_VPS_IP
cd /opt/cortex
docker-compose -f docker-compose.prod.yaml ps
# Should show: app, worker-default, worker-embeddings, worker-hf all "Up"
```

---

## 📋 Documentation Files Created

### For Development
- **`PRE_DEPLOYMENT_CHECKLIST.md`** - Quick reference for pre-deployment tasks
- **`PRODUCTION_HARDENING.md`** - Detailed code examples for all 5 critical fixes

### For Deployment
- **`DEPLOYMENT.md`** - Complete 5-phase VPS deployment guide
  - Phase 0: Pre-deployment fixes
  - Phase 1: VPS setup (PostgreSQL, Redis, Docker)
  - Phase 2: GitHub Actions CI/CD
  - Phase 3: Nginx & HTTPS
  - Phase 4: Monitoring
  - Phase 5: Checklist

### Updated Status
- **`docs/project-status-and-roadmap.md`** - Updated with completion status

---

## 🎯 Timeline & Effort

| Phase | Task | Effort | Timeline |
|-------|------|--------|----------|
| **0** | Code Review Findings | Done ✅ | N/A |
| **1** | Rate Limiting | 2h | Day 1 morning |
| **1** | Input Validation | 3h | Day 1 afternoon |
| **1** | Celery Error Handling | 2h | Day 2 morning |
| **1** | Query Timeouts | 1h | Day 2 midday |
| **1** | Integration Tests | 4h | Day 2-3 |
| **1** | Validation & Build | 1h | Day 3 morning |
| **2** | VPS Setup | 4h | Day 4 |
| **2** | GitHub Actions | 2h | Day 5 morning |
| **2** | Nginx & HTTPS | 1h | Day 5 afternoon |
| **2** | Deployment | 2h | Day 5-6 |
| **2** | Verification | 2h | Day 6 |
| | **TOTAL** | **24 hours** | **6 working days** |

---

## 🚨 Common Issues & Fixes

### Issue: "Import slowapi failed"
```bash
# Fix
uv add slowapi
# or
pip install slowapi
```

### Issue: "Celery tasks not processing"
```bash
ssh cortex@YOUR_VPS_IP
docker-compose -f docker-compose.prod.yaml logs worker-default
# Check for errors, restart if needed
docker-compose -f docker-compose.prod.yaml restart worker-default
```

### Issue: "Certificate not trusted"
```bash
# Verify Let's Encrypt setup
sudo certbot status
sudo systemctl status certbot.timer

# Renew manually if needed
sudo certbot renew --force-renewal
```

### Issue: "Database connection timeout"
```bash
ssh cortex@YOUR_VPS_IP
# Check PostgreSQL
sudo systemctl status postgresql
# Check logs
docker-compose -f docker-compose.prod.yaml logs db
```

### Issue: "Out of memory"
```bash
ssh cortex@YOUR_VPS_IP
free -h
# If needed, upgrade VPS size or add swap
# (See DEPLOYMENT.md scaling section)
```

---

## 📞 What's Next After Deployment?

### Week 3: Monitoring (Post-deployment)
- [ ] Set up Prometheus metrics
- [ ] Configure health check alerts
- [ ] Monitor database slow logs
- [ ] Check Celery queue depths

### Week 4: Scale & Harden
- [ ] Implement RBAC system
- [ ] Add audit logging
- [ ] Optimize full-text search
- [ ] Add graceful degradation

### Week 5: Frontend
- [ ] Deploy Next.js frontend
- [ ] Set up OAuth callbacks
- [ ] Configure CORS properly

---

## ✨ Success Criteria

You're ready for production when:

✅ **Code Quality**
- All linting passes: `ruff check src`
- All type checking passes: `pyright src`
- 50+ tests passing: `pytest tests/`

✅ **Security**
- Rate limiting enforced
- Input validation comprehensive
- OAuth flows working
- HTTPS certificate valid

✅ **Reliability**
- Error handling classified and tested
- Database query timeouts set
- Celery workers stable
- Health checks passing

✅ **Deployment**
- Docker images built
- GitHub Actions pipeline running
- VPS fully configured
- Zero-downtime deployment works

✅ **Operations**
- Logs aggregated and searchable
- Monitoring alerts configured
- Backup strategy implemented
- Runbooks documented

---

## 🎓 Learning Resources

### Architecture & Patterns
- Clean Architecture by Robert C. Martin
- FastAPI Best Practices: https://fastapi.tiangolo.com/
- SQLAlchemy 2.0 Async: https://docs.sqlalchemy.org/

### Security
- OWASP Top 10: https://owasp.org/www-project-top-ten/
- JWT Best Practices: https://tools.ietf.org/html/rfc7519
- SSRF Prevention: https://portswigger.net/web-security/ssrf

### DevOps
- Docker Best Practices: https://docs.docker.com/develop/dev-best-practices/
- GitHub Actions: https://docs.github.com/en/actions
- Nginx Configuration: https://nginx.org/en/docs/

---

## 📝 Quick Command Reference

```bash
# Development
cd /Users/maksympushkash/cortex
uv run pytest tests/
uv run ruff check src
uv run pyright src

# Local Docker
docker build -f Dockerfile -t cortex:latest .
docker-compose up -d

# VPS Deployment
ssh cortex@YOUR_VPS_IP
cd /opt/cortex
docker-compose -f docker-compose.prod.yaml up -d
docker-compose -f docker-compose.prod.yaml logs -f

# GitHub Actions
git push origin main  # Triggers CI/CD pipeline
# View: https://github.com/YOUR_REPO/actions

# Monitoring
curl https://cortex.yourdomain.com/health/ready
```

---

## 📚 Reference Documents

- **PRE_DEPLOYMENT_CHECKLIST.md** - What to fix (overview)
- **PRODUCTION_HARDENING.md** - How to fix (detailed code)
- **DEPLOYMENT.md** - How to deploy (infrastructure)
- **docs/project-status-and-roadmap.md** - Project status

---

**Status: Ready for deployment** ✅

**Your codebase is solid. Implement the 5 hardening fixes (12 hours), deploy to VPS (6 hours), and you're production-ready.**

*Last updated: May 2026*
