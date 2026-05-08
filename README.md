# Cortex

Cortex is a personal knowledge base for indexing and searching your content. Upload PDFs, articles, links, voice. The system chunks content, generates embeddings, indexes them, and answers natural language questions with sources and citations.

**TL;DR:** Personal knowledge base + AI chat with citations.

- App: https://cortexx.me/
- Frontend: https://github.com/MaksymPushkash/cortex_client

---

## How It Works

```
User → Uploads content (text, PDF, URL, YouTube video URL, audio, image)
       ↓
     Asynchronous pipeline (Celery workers)
       → Extract text (pdfplumber, trafilatura, whisper, tesseract)
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
   - Extract text (format-aware: PDF, URL, audio, image)
   - Split into chunks (semantic-aware)
   - Batch embed via OpenAI
   - Auto-tag with HF NER
   - Save to PostgreSQL
3. Redis status → frontend polls `/documents/{id}/status`
4. Ready → `status: ready`

**Content types:**
- PDF → pdfplumber
- URL → trafilatura
- Audio/voice → OpenAI whisper
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

### Configuration

- **Nginx:** `/etc/nginx/sites-available/api.cortexx.me` (HTTPS + SSE + streaming)
- **Environment:** `.env.production` in `/opt/cortex/`
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

Status: **220 tests passing**, mypy clean, ruff clean.

---

## Features (MVP)

✅ Document ingestion (PDF, URL, audio, image)  
✅ Asynchronous processing (Celery + RabbitMQ)  
✅ Hybrid retrieval (BM25 + pgvector)  
✅ LLM synthesis + streaming  
✅ REFRAG context packaging + citations  
✅ RAGAS eval scoring  
✅ JWT auth + OAuth2  
✅ Rate limiting + input validation  
✅ Prometheus metrics + Grafana dashboards  
✅ Nginx + HTTPS
✅ Web UI (Next.js, TypeScript, React, TanStack Query, Zustand, Tailwind CSS, shadcn) Deployed on Vercel

✅ AWS S3 Storage

---

## Roadmap

- [ ] Managed media worker (separate VPS)
- [ ] Role-based access (teams)
- [ ] Audit logs
- [ ] SaaS pricing

---

## Documentation


- [Public API](docs/public-api.md)
- [Local Development](docs/local-development.md)

---

