# Conserium

Conserium is a personal knowledge base for indexing and searching your content. Upload PDFs, articles, links. The system chunks content, generates embeddings, indexes them, and answers natural language questions with sources and citations.

**TL;DR:** Personal knowledge base + AI chat with citations.

- App: https://conserium.app/
- Frontend: https://github.com/MaksymPushkash/conserium_client

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
| **Background Jobs** | Celery, Redis |
| **Database** | PostgreSQL 16 + pgvector |
| **Cache** | Redis |
| **Embeddings** | OpenAI (text-embedding-3-small) |
| **NLP Models** | HuggingFace (NER, whisper, reranker) |
| **Orchestration** | LangGraph (multi-agent) |
| **Observability** | Langfuse, Prometheus, Grafana |
| **Architecture** | Feature-first modular monolith |
| **Dependency Injection** | FastAPI dependencies |
| **Async ORM** | SQLAlchemy 2.0+ |
| **Deployment** | Docker Compose, Nginx, Let's Encrypt |

---

## Architecture

Conserium is a feature-first modular monolith modeled after Polar's backend structure.
Each package under `src/` owns its HTTP endpoints, schemas, business services,
repositories, authorization dependencies, and background tasks. Shared framework code
lives in `src/kit`, SQLAlchemy models live in `src/models`, API composition lives in
`src/api.py`, and Celery composition lives in `src/worker`.

```text
src/
├── api.py                 # Central /api/v1 router
├── postgres.py            # Async session dependencies and transaction boundary
├── models/                # Shared SQLAlchemy models
├── kit/                   # Cross-cutting helpers and external adapter protocols
├── worker/                # Celery app, queues, registry, and task names
└── {feature}/
    ├── endpoints.py       # Thin FastAPI handlers
    ├── schemas.py         # API and feature data contracts
    ├── service.py         # Business orchestration
    ├── repository.py      # SQLAlchemy query ownership
    ├── auth.py            # Feature authorization dependencies
    └── tasks.py           # Feature-owned Celery tasks when needed
```

See [Architecture](docs/architecture.md) for module rules, request and worker flows,
transaction ownership, frontend API contracts, deployment boundaries, and remaining
structural debt.

### Workers

Three Celery worker processes and one Celery Beat scheduler run in production:

- **worker-default** — `document_processing`, `notifications`, and `cleanup` queues
- **worker-embeddings** — `embeddings` queue for OpenAI embedding work
- **worker-media** — `media_processing` and `hf_processing` queues for CPU-heavy work
- **scheduler** — dispatches repo sync, outbox drain, and optional notification jobs

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
docker compose up -d postgres redis

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
cd /opt/conserium
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

- `VPS_APP_DIR` optional, defaults to `/opt/conserium`

The VPS user must be able to run:

```bash
cd "$VPS_APP_DIR"
git fetch origin main
docker compose up -d --build --remove-orphans
docker compose exec -T app uv run alembic upgrade head
```

### Configuration

- **Nginx:** `/etc/nginx/sites-available/api.conserium.app` (HTTPS + SSE + streaming)
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

### Implemented

- Document ingestion for PDF, URL, YouTube, image, text, markdown, public API payloads, webhooks, Notion pages, Anytype exports, browser extension saves, and Telegram-forwarded content
- Durable document processing outbox and repo sync outbox for retryable background dispatch
- Processing Center with active/failed jobs, retry flows, clear reasons, and per-document processing state
- Notes with versions, restore, image upload, document indexing, and conversion from graph/gap workflows
- Auto summaries, tags, entities, categories, suggested questions, visual metadata, and manual tag routing
- Hybrid retrieval with semantic search, REFRAG packaging, citations, streaming SSE, query persistence, and suggested follow-up questions
- Chat scopes for all workspace, document, collection, and topic contexts
- Library search, filters, document details, metadata cleanup, retry/reprocess, delete, bulk move, bulk tags, and bulk Markdown export
- Collection workspaces with documents, topics, gaps, recent Q&A, recent drafts, recent comparisons, share/export actions, quick sidebar access, and workspace-scoped filters
- Team workspaces with workspace-owned collections, inherited roles, member invite/update/remove, owner transfer, shared ingestion, and workspace audit trail
- Drafts v2 with scoped generation, templates, editable outlines, persisted versions, restore, and Markdown export
- Compare v2 with selected documents, explicit dimensions, persisted history, evidence tables, synthesis note and decision memo actions
- Knowledge Graph v2 with filters, node details, graph insights, topic actions, topic rename/merge/pin/ignore, and topic pages
- Knowledge Gaps v2 with collection/topic coverage, why-detected rationale, missing source types, suggested actions, note creation, and collection integration
- Learning goals with resources, completion tracking, reminders, and recommended resource refresh
- Review learning foundation with flashcards, spaced-repetition review, quiz generation/history/retry, weak-area feedback, and learning paths with ordered steps
- Dashboard onboarding, activity timeline, due review metrics, daily digest questions, weekly report summary, and actionable empty states
- Public collection shares, collection share controls, public collection Ask, shareable answers with citations, public answer pages, owner controls, quotas, and abuse/audit logging
- GitHub markdown repo sync with include/exclude filters, per-file status, truncated-tree protection, partial raw-file warnings, and durable outbox dispatch
- Notion OAuth, page search/import, Notion export, and integration settings
- Public API keys with scopes, hashed storage, last-used tracking, revocation, public ingest, status, collection list, and query endpoints
- Webhook ingestion with idempotency, provider metadata, collection/tag routing, and intake status/retry records
- Telegram pairing backend, chat bindings, revocation, and Telegram adapter MVP
- Browser extension scaffold with API-key validation, collection picker, origin validation, selected-text/current-tab save, save history, and release/install docs
- Markdown, PDF, and Notion export
- Settings for account, privacy, AI preferences, API keys, Notion, Telegram pairing, and browser/bookmarklet capture
- Command palette with recent actions and global drag-and-drop ingestion
- JWT auth, OAuth integrations, rate limiting, Prometheus, Grafana, Langfuse, Docker deployment, and S3-compatible file storage

### Partially Implemented

- Scheduled proactive delivery is still limited: daily digest, weekly report, and reminders exist as product surfaces/state, but Telegram/email delivery is intentionally not a current priority
- Team workspace polish is underway: core workspaces, roles, owner transfer, shared ingestion, and audit trail exist; remaining work is workspace rename/delete, confirmation UX, richer audit filters, and app-shell workspace switching
- Browser extension is beyond scaffold but still needs production packaging hardening, broader failure recovery, and release QA
- Telegram bot remains MVP-level; richer media support and delivery/status polish remain

---

## Roadmap

### Current Engineering Priorities

- [x] Smart connections v1: related documents, overlap reasons, document detail panel, and Telegram response hints
- [x] Review learning foundation: flashcard generation, spaced repetition state, Review page, and document/topic/collection review scopes
- [x] Quiz mode v1: generated questions, answer checking, quiz history/retry, and weak-area feedback into Goals/Gaps
- [x] Learning Path mode v1: ordered plan from topic/document/collection, persisted path steps, progress, and regeneration
- [x] Public knowledge workflows v1: public collection Ask, shareable answers with citations, public answer pages, abuse controls, quotas, and owner management
- [x] Shared workspace foundation: team ownership, members, roles, shared ingestion, audit trail, team collections, and owner transfer
- [ ] Finish workspace polish: rename/delete workspace, owner-transfer confirmation, app-shell workspace switcher, audit filters, and stronger upload-route integration tests
- [ ] Harden browser extension: packaged release, token storage review, failure recovery, save-history polish, and final release QA
- [ ] Optimize collection workspace aggregate loading and large dashboard queries
- [ ] Harden Telegram bot when cost allows: forwarded files/images/voice, collection selection, status replies, duplicate detection, and production deployment docs
- [ ] Finish scheduled proactive delivery when cost allows: daily digest via Telegram/email, digest history, answer state, weekly report delivery, and goal reminder delivery

### Later Product Work

- [ ] Notion periodic resync with cursors, deleted/stale page handling, and Processing Center jobs
- [ ] Anytype direct connector if the API surface is stable enough; keep Markdown/JSON import as fallback
- [ ] Conflict detector v2 with background claim extraction
- [ ] Explain mode and answer style presets: beginner, experienced, tutor, architect
- [ ] Role-based access control, audit logs, billing, and organization administration
- [ ] Public API documentation examples for Zapier, Make, n8n, IFTTT, scripts, Telegram, and browser extension usage

---

## Documentation

- [Architecture](docs/architecture.md)
- [Public API](docs/public-api.md)
- [Local Development](docs/local-development.md)

---
