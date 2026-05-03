# Cortex VPS Deployment Guide

## Executive Summary

This guide covers deploying Cortex to a VPS with GitHub Actions CI/CD pipeline, HTTPS/TLS, and production-grade infrastructure.

**Deployment Architecture:**
```
GitHub Actions (CI/CD)
    ↓
Docker Registry (ghcr.io)
    ↓
VPS (Ubuntu 22.04 LTS)
    ├── Nginx (reverse proxy, TLS)
    ├── FastAPI app (Uvicorn, 4 workers)
    ├── PostgreSQL 15
    ├── Redis
    ├── Celery workers (3 queues: document_processing, embeddings, hf_processing)
    └── Monitoring (node_exporter, prometheus optional)
```

---

## Phase 0: Pre-Deployment Fixes (CRITICAL - Do This First)

### 1. Add Rate Limiting (2 hours)

**Install:**
```bash
uv add slowapi
```

**Create `src/presentation/middleware/rate_limit.py`:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, HTTPException

limiter = Limiter(key_func=get_remote_address)

def setup_rate_limiting(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

async def rate_limit_exceeded_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests"},
    )
```

**Add to main.py:**
```python
from src.presentation.middleware.rate_limit import setup_rate_limiting

app = FastAPI()
setup_rate_limiting(app)

# Apply to key endpoints
@app.post("/api/v1/query")
@limiter.limit("100/minute")
async def query_documents(...):
    pass

@app.post("/api/v1/ingest")
@limiter.limit("50/minute")
async def ingest_document(...):
    pass
```

### 2. Add Input Validation Constraints (3 hours)

**Update `src/presentation/schemas/query_schemas.py`:**
```python
from pydantic import Field

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    conversation_id: UUID | None = None
    collection_id: UUID | None = None
    limit: int = Field(default=10, ge=1, le=50)
```

**Update `src/presentation/schemas/document_schemas.py`:**
```python
class CreateDocumentRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    type: DocumentType
    source_url: HttpUrl | None = None
    raw_content: str | None = Field(None, max_length=1_000_000)
```

### 3. Fix Celery Error Handling (2 hours)

**Update `src/infrastructure/celery/tasks/document_processing.py`:**
```python
@celery_app.task(queue="document_processing", bind=True, max_retries=3)
def process_document_task(self: Any, document_id: str) -> dict[str, str]:
    try:
        result = asyncio.run(_run_use_case(document_id))
        return result
    except (OpenAIError, RequestException) as exc:
        # Retryable errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc) from exc
        _handle_failure(document_id, f"Permanent API failure: {exc}", log)
        return {"document_id": document_id, "status": "FAILED"}
    except (DocumentNotFoundException, ValueError) as exc:
        # Logic errors - don't retry
        _handle_failure(document_id, f"Logic error: {exc}", log)
        return {"document_id": document_id, "status": "FAILED"}
    except Exception as exc:
        # Unknown - log and fail
        log.exception("Unknown error", error=exc)
        _handle_failure(document_id, f"Unknown error: {exc}", log)
        return {"document_id": document_id, "status": "FAILED"}
```

### 4. Add Database Query Timeouts (1 hour)

**Update PostgreSQL connection in `src/infrastructure/database/sql_alchemy.py`:**
```python
engine = create_async_engine(
    settings.DATABASE_URL,
    connect_args={
        "timeout": 10,  # Connection timeout
        "command_timeout": 30,  # Query timeout
    },
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
)
```

### 5. Add Integration Tests (4 hours)

Create `tests/integration/test_document_pipeline.py`:
```python
@pytest.mark.asyncio
async def test_document_ingestion_pipeline_end_to_end(client, db_session):
    """Test full ingestion: upload → extract → chunk → embed"""
    # Upload document
    response = await client.post("/api/v1/ingest/pdf", files={"file": pdf_bytes})
    doc_id = response.json()["document_id"]
    
    # Poll status
    for _ in range(60):  # 60 second timeout
        status = await client.get(f"/api/v1/documents/{doc_id}/status")
        if status.json()["status"] == "READY":
            break
        await asyncio.sleep(1)
    
    assert status.json()["status"] == "READY"
    
    # Verify document in database
    async with db_session() as session:
        doc = await session.get(Document, doc_id)
        assert doc is not None
        assert doc.chunk_count > 0

@pytest.mark.asyncio
async def test_query_with_streaming(client):
    """Test streaming query endpoint"""
    response = await client.post(
        "/api/v1/query/stream",
        json={"query": "What is machine learning?"}
    )
    
    chunks = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            chunks.append(json.loads(line[6:]))
    
    assert len(chunks) > 0
    assert chunks[-1]["type"] == "done"
```

---

## Phase 1: VPS Setup (Days 1-2)

### VPS Requirements

- **Provider:** Linode, DigitalOcean, or Hetzner
- **OS:** Ubuntu 22.04 LTS
- **CPU:** Minimum 4 cores (for Celery workers)
- **RAM:** Minimum 8GB (FastAPI + PostgreSQL + Redis)
- **Storage:** 50GB+ SSD
- **Network:** Public IPv4, domain name

### Step 1: Initial VPS Setup

```bash
#!/bin/bash
# SSH into VPS as root

# Update system
apt update && apt upgrade -y

# Install dependencies
apt install -y \
    curl \
    wget \
    git \
    vim \
    htop \
    net-tools \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    python3-pip \
    python3-venv \
    postgresql \
    postgresql-contrib \
    redis-server \
    nginx \
    certbot \
    python3-certbot-nginx \
    docker.io \
    docker-compose \
    supervisor

# Create app user
useradd -m -s /bin/bash cortex
usermod -aG docker cortex

# Create app directory
mkdir -p /opt/cortex
chown -R cortex:cortex /opt/cortex
```

### Step 2: PostgreSQL Setup

```bash
# As root
sudo -u postgres psql

# In psql:
CREATE DATABASE cortex_db;
CREATE USER cortex_user WITH PASSWORD 'YOUR_SECURE_PASSWORD';
ALTER ROLE cortex_user SET client_encoding TO 'utf8';
ALTER ROLE cortex_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE cortex_user SET default_transaction_deferrable TO on;
ALTER ROLE cortex_user SET default_transaction_readonly TO off;
GRANT ALL PRIVILEGES ON DATABASE cortex_db TO cortex_user;
\q
```

**Tune PostgreSQL for production** (`/etc/postgresql/15/main/postgresql.conf`):
```ini
max_connections = 200
shared_buffers = 2GB
effective_cache_size = 6GB
maintenance_work_mem = 512MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
```

### Step 3: Redis Setup

```bash
# Edit /etc/redis/redis.conf
sudo nano /etc/redis/redis.conf

# Set:
maxmemory 2gb
maxmemory-policy allkeys-lru
requirepass YOUR_REDIS_PASSWORD

# Restart
sudo systemctl restart redis-server
```

### Step 4: Docker & Application Setup

```bash
cd /opt/cortex
sudo -u cortex git clone https://github.com/YOUR_REPO/cortex.git .

# Create .env file
sudo -u cortex cat > .env << 'EOF'
# Core
DEBUG=false
FRONTEND_URL=https://cortex.yourdomain.com

# JWT
JWT_SECRET=$(openssl rand -hex 32)
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# Database
DATABASE_URL=postgresql+asyncpg://cortex_user:PASSWORD@localhost:5432/cortex_db

# Redis
REDIS_URL=redis://:PASSWORD@localhost:6379

# Celery
CELERY_BROKER_URL=redis://:PASSWORD@localhost:6379/0
CELERY_RESULT_BACKEND=redis://:PASSWORD@localhost:6379/1

# OpenAI
OPENAI_API_KEY=YOUR_KEY
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_LLM_MODEL=gpt-4o-mini

# OAuth
GOOGLE_CLIENT_ID=YOUR_ID
GOOGLE_CLIENT_SECRET=YOUR_SECRET
GITHUB_CLIENT_ID=YOUR_ID
GITHUB_CLIENT_SECRET=YOUR_SECRET

# Storage
FILE_STORAGE_TYPE=local
LOCAL_STORAGE_PATH=/opt/cortex/storage

# Reranker
RERANKER_ENABLED=true
RERANKER_TOP_K=10
EOF

# Create docker-compose override for production
sudo -u cortex cat > docker-compose.prod.yaml << 'EOF'
version: '3.8'
services:
  app:
    image: ${REGISTRY}/cortex:${VERSION}
    environment:
      - ENVIRONMENT=production
    restart: always
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - /opt/cortex/storage:/app/storage
    depends_on:
      - db
      - redis
    
  worker-default:
    image: ${REGISTRY}/cortex-worker:${VERSION}
    command: celery -A src.infrastructure.celery.app worker -Q document_processing,notifications,cleanup --concurrency=4
    environment:
      - ENVIRONMENT=production
    restart: always
    depends_on:
      - db
      - redis
  
  worker-embeddings:
    image: ${REGISTRY}/cortex-worker:${VERSION}
    command: celery -A src.infrastructure.celery.app worker -Q embeddings --concurrency=8
    environment:
      - ENVIRONMENT=production
    restart: always
    depends_on:
      - db
      - redis
  
  worker-hf:
    image: ${REGISTRY}/cortex-worker:${VERSION}
    command: celery -A src.infrastructure.celery.app worker -Q hf_processing --concurrency=2
    environment:
      - ENVIRONMENT=production
    restart: always
    depends_on:
      - db
      - redis

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: cortex_db
      POSTGRES_USER: cortex_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: always
    
  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    restart: always

volumes:
  postgres_data:
  redis_data:
EOF

# Build and start containers
sudo -u cortex docker-compose -f docker-compose.prod.yaml up -d
```

---

## Phase 2: GitHub Actions CI/CD Pipeline

### Step 1: Create GitHub Secrets

In GitHub repo Settings → Secrets and variables → Actions, add:
- `REGISTRY_TOKEN` - GitHub Container Registry token
- `REGISTRY_USERNAME` - Your GitHub username
- `VPS_HOST` - VPS IP or hostname
- `VPS_USER` - SSH user (cortex)
- `VPS_SSH_KEY` - Private SSH key
- `VPS_KNOWN_HOSTS` - VPS public key fingerprint

### Step 2: Create GitHub Actions Workflow

`.github/workflows/deploy.yml`:
```yaml
name: Build & Deploy

on:
  push:
    branches: [main]
    paths:
      - 'src/**'
      - 'Dockerfile*'
      - '.github/workflows/deploy.yml'
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: test_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          pip install uv
          uv pip install -e .
      
      - name: Lint with ruff
        run: uv run ruff check src tests --fix
      
      - name: Type check
        run: uv run pyright src
      
      - name: Run tests
        env:
          DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379
          OPENAI_API_KEY: sk-test-key
        run: uv run pytest tests/unit -v --cov=src --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml

  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      
      - name: Log in to Container Registry
        uses: docker/login-action@v2
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.REGISTRY_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v4
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha
      
      - name: Build and push app image
        uses: docker/build-push-action@v4
        with:
          context: .
          file: ./Dockerfile
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=registry,ref=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:buildcache
          cache-to: type=registry,ref=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:buildcache,mode=max
      
      - name: Build and push worker image
        uses: docker/build-push-action@v4
        with:
          context: .
          file: ./Dockerfile.celery
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}

  deploy:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v3
      
      - name: Deploy to VPS
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /opt/cortex
            docker-compose -f docker-compose.prod.yaml pull
            docker-compose -f docker-compose.prod.yaml up -d
            docker-compose -f docker-compose.prod.yaml exec -T app alembic upgrade head
            docker-compose -f docker-compose.prod.yaml logs -f --tail=100 app
```

---

## Phase 3: Nginx & HTTPS Setup

### Step 1: Configure Nginx

`/etc/nginx/sites-available/cortex`:
```nginx
# Redirect HTTP to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name cortex.yourdomain.com;
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name cortex.yourdomain.com;
    
    # SSL certificates (certbot-managed)
    ssl_certificate /etc/letsencrypt/live/cortex.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cortex.yourdomain.com/privkey.pem;
    
    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Logging
    access_log /var/log/nginx/cortex_access.log;
    error_log /var/log/nginx/cortex_error.log;
    
    # Proxy to FastAPI
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # SSE streaming
    location /api/v1/query/stream {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Disable buffering for streaming
        proxy_buffering off;
        proxy_request_buffering off;
        
        # Longer timeout for streams
        proxy_read_timeout 600s;
    }
}
```

Enable site and test:
```bash
sudo ln -s /etc/nginx/sites-available/cortex /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Step 2: SSL Certificate Setup

```bash
# Get certificate from Let's Encrypt
sudo certbot certonly --nginx -d cortex.yourdomain.com

# Auto-renewal (already configured in certbot)
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

---

## Phase 4: Monitoring & Logging

### Add Health Check Endpoint

`src/presentation/api/v1/health.py`:
```python
from fastapi import APIRouter
from src.core.config import settings

router = APIRouter(prefix="/health", tags=["health"])

@router.get("/")
async def health_check() -> dict[str, str]:
    """Basic health check"""
    return {"status": "ok"}

@router.get("/live")
async def liveness_probe() -> dict[str, str]:
    """Kubernetes liveness probe"""
    return {"status": "alive"}

@router.get("/ready")
async def readiness_probe(
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> dict[str, str]:
    """Kubernetes readiness probe"""
    try:
        # Check database
        await db.execute(text("SELECT 1"))
        
        # Check Redis
        await redis.ping()
        
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not_ready", "error": str(e)}, 503
```

### Configure Nginx Health Checks

Add to `docker-compose.prod.yaml`:
```yaml
app:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health/ready"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 40s
```

### Setup Log Rotation

`/etc/logrotate.d/cortex`:
```
/var/log/cortex/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 cortex cortex
    sharedscripts
    postrotate
        systemctl reload nginx > /dev/null 2>&1 || true
    endscript
}
```

---

## Phase 5: Deployment Checklist

### Pre-Deployment
- [ ] Run all tests locally
- [ ] Update version in `pyproject.toml`
- [ ] Create git tag: `git tag v1.0.0`
- [ ] Push: `git push origin main --tags`
- [ ] Verify GitHub Actions passed

### VPS Setup
- [ ] Domain DNS points to VPS IP
- [ ] SSH access configured
- [ ] PostgreSQL running and initialized
- [ ] Redis running
- [ ] `.env` file created with all secrets
- [ ] Docker containers built and running

### Post-Deployment
- [ ] Verify HTTPS certificate (green lock in browser)
- [ ] Run smoke tests against production API
- [ ] Verify OAuth flows work
- [ ] Test document ingestion end-to-end
- [ ] Monitor logs for errors: `docker-compose logs -f`

### First Week Monitoring
- [ ] Check error rates daily
- [ ] Monitor database connection pool
- [ ] Watch Celery queue depths
- [ ] Verify embeddings cache hit rate
- [ ] Review slow query logs

---

## Scaling Considerations (Phase 2)

### Horizontal Scaling
```bash
# Run multiple Uvicorn workers behind Nginx
# Already configured in docker-compose (4 workers via environment)

# Scale Celery workers independently
docker-compose -f docker-compose.prod.yaml up -d --scale worker-embeddings=2 worker-hf=3
```

### Database Optimization
```sql
-- Create indexes
CREATE INDEX idx_documents_user_created ON documents(user_id, created_at DESC);
CREATE INDEX idx_chunks_doc ON chunks(document_id);
CREATE INDEX idx_chunks_embedding ON chunks USING HNSW(embedding);

-- Enable pgvector
CREATE EXTENSION vector;
```

### Redis Persistence
```ini
# /etc/redis/redis.conf
appendonly yes
appendfsync everysec
```

---

## Rollback Strategy

### To Rollback a Deployment

```bash
ssh cortex@VPS_IP
cd /opt/cortex

# View deployment history
docker image ls | grep cortex

# Rollback to previous version
docker-compose -f docker-compose.prod.yaml down
docker pull ghcr.io/your-repo/cortex:previous-tag
docker-compose -f docker-compose.prod.yaml up -d
```

---

## Emergency Procedures

### Database Backup

```bash
# Daily backup
0 2 * * * pg_dump -U cortex_user -d cortex_db | gzip > /backups/cortex_$(date +\%Y\%m\%d).sql.gz

# Test restore
gunzip < /backups/cortex_20260503.sql.gz | psql -U cortex_user -d cortex_db
```

### Clear Redis Cache

```bash
redis-cli -a YOUR_PASSWORD FLUSHDB
```

### Restart All Services

```bash
cd /opt/cortex
docker-compose -f docker-compose.prod.yaml restart
```

---

## Success Criteria

Your deployment is successful when:

✅ HTTPS connection established and verified
✅ API responds at https://cortex.yourdomain.com
✅ Health checks pass: `curl https://cortex.yourdomain.com/health/ready`
✅ Documents can be ingested and queried
✅ OAuth2 flows work (Google, GitHub)
✅ Celery workers processing tasks
✅ Logs show no errors

---

## Next Steps After Deployment

1. **Week 1:** Monitor production metrics, fix any issues
2. **Week 2:** Set up monitoring dashboard (Prometheus/Grafana)
3. **Week 3:** Implement RBAC system
4. **Week 4:** Deploy frontend (Next.js)

---

*Last updated: May 2026*
