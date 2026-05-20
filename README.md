# Cortex

Cortex is a personal knowledge base for indexing and searching your content. Upload PDFs, articles, links. The system chunks content, generates embeddings, indexes them, and answers natural language questions with sources and citations.

**TL;DR:** Personal knowledge base + AI chat with citations.

- App: https://cortexx.me/
- Frontend: https://github.com/MaksymPushkash/cortex_client

---

## How It Works

```
User → Uploads content (text, PDF, URL, YouTube video URL, image)
       ↓
     Asynchronous pipeline (Celery workers)
       → Extract text (pdfplumber, trafilatura, tesseract)
       → Split into chunks
       → Generate embeddings (OpenAI)
       → Auto-tagging (HF NER)
       → Store in PostgreSQL + pgvector
       ↓
     Query → Hybrid retrieval (BM25 + semantic)
            → Rerank (cross-encoder)
            → LLM synthesis (streaming SSE)
            → Citations + RAGAS eval
            ↓
          Answer with sources
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **API** | FastAPI, Pydantic, async |
| **Background Jobs** | Celery, RabbitMQ |
| **Database** | PostgreSQL 16 + pgvector |
| **Cache** | Redis |
| **Embeddings** | OpenAI (text-embedding-3-small) |
| **NLP Models** | HuggingFace (NER, whisper, reranker) |
| **Orchestration** | LangGraph (multi-agent) |
| **Observability** | Langfuse, Prometheus, Grafana |
| **Architecture** | Clean Architecture + CQRS patterns |
| **DI Container** | Dishka |
| **Async ORM** | SQLAlchemy 2.0+ |
| **Deployment** | Docker Compose, Nginx, Let's Encrypt |

---

## Architecture

### Layers

```
Presentation → API Routes (FastAPI)
    ↓
Application → Use Cases, Agents (LangGraph), DTOs
    ↓
Domain → Entities, Value Objects, Business Logic
    ↓
Infrastructure → SQLAlchemy, Celery, External Services
```



### Workers

Four separate Celery workers for parallel processing:

- **document_processing** — extract → chunk → tag (general pipeline)
- **embeddings** — OpenAI API calls (rate-limited)
- **media_processing** — CPU-heavy media/enrichment models (separate Docker image)
- **cleanup** — periodic maintenance tasks

---

## Ingestion Pipeline

1. `POST /ingest` → 202 Accepted with `document_id`
2. Celery task processes:
   - Extract text (format-aware: PDF, URL, image)
   - Split into chunks (semantic-aware)
   - Batch embed via OpenAI
   - Auto-tag with HF NER
   - Save to PostgreSQL
3. Redis status → frontend polls `/documents/{id}/status`
4. Ready → `status: ready`

**Content types:**
- PDF → pdfplumber
- URL → trafilatura
- Images → Tesseract (OCR) or LLaVA (vision)
- YouTube → transcript API

---

## Query + REFRAG

1. `POST /query` with question text
2. LangGraph routing:
   - RouterAgent → determines type (search / summary / etc)
   - RetrievalAgent → hybrid BM25 + pgvector
   - RerankerAgent → cross-encoder sorting
   - SynthesisAgent → LLM + streaming SSE with REFRAG (Referenced Fragment packaging)
   - EvalAgent → RAGAS scoring
3. Streaming response with citations: `[1] Source A`, `[2] Source B`

**REFRAG** — context-oriented fragment packaging: document chunks are referenced, ranked, and assembled into a structured package with metadata and sources before generation. This improves citation accuracy and response stability.

---

## Local Setup

### Requirements

- Docker, Docker Compose
- Python 3.12+ (for development)
- uv (package manager)

### Start

```bash
# 1) Setup
docker compose up -d postgres redis rabbitmq

# 2) Migrations
uv run alembic upgrade head

# 3) Run all services
docker compose up -d

# 4) API
open http://localhost:8000/docs
```

API available at `http://localhost:8000/docs` (Swagger).

---

## Production Deployment (VPS)

### Quick Deploy

```bash
# On VPS
cd /opt/cortex
git pull
docker compose up -d --build
docker compose exec -T app uv run alembic upgrade head
```

### GitHub Actions Deploy

Production deploy runs after `Eval Regression` succeeds on `main`.

Required repository secrets:

- `VPS_HOST`
- `VPS_USER`
- `VPS_SSH_PRIVATE_KEY`
- `VPS_PORT` optional, defaults to `22`

Required repository variable:

- `VPS_APP_DIR` optional, defaults to `/opt/cortex`

The VPS user must be able to run:

```bash
cd "$VPS_APP_DIR"
git fetch origin main
docker compose up -d --build --remove-orphans
docker compose exec -T app uv run alembic upgrade head
```

### Configuration

- **Nginx:** `/etc/nginx/sites-available/api.cortexx.me` (HTTPS + SSE + streaming)
- **Environment:** `.env.prod` in the deployment directory
- **Observability:** Prometheus `:9090`, Grafana `:3000` (SSH tunnel only)

### VPS Requirements

- 2+ CPU, 4+ GB RAM (including swap)
- Ubuntu 22.04 LTS
- Docker, Docker Compose

---

## Monitoring

### Endpoints

- `GET /health` → health check
- `GET /metrics` → Prometheus format

### Metrics

- Query latency (avg, p95)
- Embedding cache hit rate
- Queue depth per queue
- RAGAS eval scores (faithfulness, relevancy)
- OpenAI API costs

### Grafana Dashboard

At `http://localhost:3000`
Latency metrics calculated on 5-minute sliding window for real-time monitoring.

---

## Testing

```bash
# All tests
uv run pytest tests/ -v

# Unit only
uv run pytest tests/unit -v

# Eval regression
uv run python scripts/run_eval_harness.py
```

Status: unit tests, mypy, ruff, and frontend build are expected to pass before deploy.

---

## Features

- Document ingestion for PDF, URL, YouTube, image, text, and markdown
- Notes with versions, restore, image upload, and memory indexing
- Auto summaries, tags, entities, categories, suggested questions, and visual metadata
- Hybrid retrieval with semantic search, REFRAG packaging, citations, streaming, and evaluation
- Chat history, contextual follow-up queries, and source activity tracking
- Library search, filters, collections, document details, exports, retry, and reprocess
- Dashboard stats, activity temperature, learning timeline, topics, and topic detail pages
- Draft generation from saved knowledge with source constraints
- Compare mode and conflict detection v1
- Knowledge graph v1 and knowledge gaps v1
- Learning goals with resources and completion tracking
- Public collection pages with share controls
- GitHub markdown repo sync v1
- Markdown, PDF, and Notion export
- Settings for account, privacy, AI preferences, and integrations
- Command palette and global drag-and-drop ingestion
- JWT auth, OAuth integrations, rate limiting, Prometheus, Grafana, Langfuse, and Docker deployment
- S3-compatible file storage

---

## Roadmap

- [ ] Notion page picker hardening and token key rotation tooling
- [ ] Persistent learning resource cache with scheduled refresh
- [ ] GitHub sync hardening: auth scopes, rate limits, duplicate handling, and sync conflicts
- [ ] Public knowledge pages security review and analytics
- [ ] Export polish for Markdown/PDF/Notion
- [ ] Knowledge gaps v2 with cached rubrics
- [ ] Conflict detector v2 with background claim extraction
- [ ] Learning goal reminders and resource plans
- [ ] Role-based access, audit logs, and billing

---

## Documentation


- [Public API](docs/public-api.md)
- [Local Development](docs/local-development.md)

---
