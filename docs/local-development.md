# Conserium Local Development

This runbook covers the feature-first modular backend: FastAPI, PostgreSQL with
pgvector, Redis, Celery workers, ingestion, query, metrics, and eval regression. See
[Architecture](architecture.md) for module ownership and dependency rules.

## Prerequisites

- Docker Desktop or Docker Engine with Compose
- Python 3.12.10
- `uv`
- Tesseract OCR if running image ingestion outside Docker
- Optional: OpenAI API key for complete embeddings/query behavior

## Required Environment

Create `.env` in the project root.

Minimal local example:

```env
DEBUG=true
JWT_SECRET=local-dev-secret-change-me
FRONTEND_URL=http://localhost:3000

DB_NAME=conserium
DB_USER=conserium
DB_PASSWORD=conserium
DATABASE_URL=postgresql+asyncpg://conserium:conserium@localhost:5432/conserium

REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/2
CELERY_RESULT_BACKEND=redis://localhost:6379/1

OPENAI_API_KEY=
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
OPENAI_LLM_MODEL=gpt-4o-mini

FILE_STORAGE_TYPE=local
LOCAL_STORAGE_PATH=./storage
AWS_REGION=eu-central-1
AWS_S3_BUCKET=
AWS_S3_PREFIX=uploads

OCR_TESSERACT_LANG=eng

LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

EVAL_SCORER=heuristic
RERANKER_ENABLED=true
RERANKER_TOP_K=10
```

Important behavior:

- `DEBUG=false` requires `OPENAI_API_KEY`.
- Complete ingestion/query quality requires `OPENAI_API_KEY` because embeddings and synthesis depend on it.
- `OPENAI_EMBEDDING_DIMENSIONS` must stay `1536`; the database/vector schema is built around that value.
- For Ukrainian image OCR, submit image documents with language `uk` or `ukr`. Docker images install `tesseract-ocr-ukr`; local non-Docker runs need the Ukrainian Tesseract language pack installed on the host.

## File Storage

Local development can use local storage:

```env
FILE_STORAGE_TYPE=local
LOCAL_STORAGE_PATH=./storage
```

Production should use S3:

```env
FILE_STORAGE_TYPE=s3
AWS_REGION=eu-central-1
AWS_S3_BUCKET=conserium-documents
AWS_S3_PREFIX=uploads
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

S3 uploads are stored as private objects. The database stores only the object key, for example:

```text
uploads/{user_id}/{uuid}-SQL_Basics_Advanced.pdf
```

Do not store presigned URLs in `documents.file_path`; generate short-lived presigned URLs later only for download or preview flows.

## Docker Flow

Start infrastructure first:

```bash
docker compose up -d postgres redis
```

Install dependencies locally:

```bash
uv sync
```

Run migrations against the Docker PostgreSQL port:

```bash
uv run alembic upgrade head
```

Build and start the full stack:

```bash
docker compose up --build
```

Services:

- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
- PostgreSQL: `localhost:5432`
- pgAdmin: `http://localhost:5050`
- Redis: `localhost:6379`
- RedisInsight: `http://localhost:5540`

Worker topology:

- `worker-default`: `document_processing`, `notifications`, `cleanup`
- `worker-embeddings`: `embeddings`
- `worker-media`: `media_processing`, `hf_processing`
- `scheduler`: Celery Beat schedules for repo sync, outbox drains, and optional notifications

Useful commands:

```bash
docker compose ps
docker compose logs -f app
docker compose logs -f worker-default
docker compose logs -f worker-embeddings
docker compose logs -f worker-media
docker compose logs -f scheduler
docker compose down
```

## Manual Local Flow

Use this when you want faster backend iteration without rebuilding containers.

Start only infrastructure:

```bash
docker compose up -d postgres redis
```

Install dependencies:

```bash
uv sync
```

Run migrations:

```bash
uv run alembic upgrade head
```

Start API:

```bash
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Start workers in separate terminals:

```bash
uv run celery -A src.worker worker --loglevel=INFO --queues=document_processing,notifications,cleanup --concurrency=4
```

```bash
uv run celery -A src.worker worker --loglevel=INFO --queues=embeddings --concurrency=4
```

```bash
uv run celery -A src.worker worker --loglevel=INFO --queues=media_processing,hf_processing --concurrency=2
```

Start Celery Beat in another terminal:

```bash
uv run celery -A src.worker beat --loglevel=INFO
```

For local media/audio/image work, install the heavier dependencies in the same environment:

```bash
uv pip install torch transformers
```

## Manual Smoke Flow

Register:

```bash
curl -s http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","password":"secret-password","display_name":"User"}'
```

Login and export token:

```bash
export ACCESS_TOKEN="$(
  curl -s http://localhost:8000/api/v1/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"email":"user@example.com","password":"secret-password"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
)"
```

Ingest text:

```bash
curl -s http://localhost:8000/api/v1/ingest \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Architecture note","type":"TEXT","raw_content":"Feature-first modules keep endpoints, services, and repositories together. PostgreSQL pgvector stores embeddings."}'
```

Poll status:

```bash
curl -s http://localhost:8000/api/v1/documents/<document_id>/status \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Query:

```bash
curl -s http://localhost:8000/api/v1/query \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query":"What did I save about feature-first architecture?","limit":5}'
```

Stream query:

```bash
curl -N http://localhost:8000/api/v1/query/stream \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query":"Summarize my saved architecture notes","limit":5}'
```

Check metrics:

```bash
curl -s http://localhost:8000/metrics
```

Run eval regression:

```bash
uv run python scripts/run_eval_harness.py --output artifacts/eval-regression-report.json
```

## OpenAPI Verification

Generate the deterministic backend contract without starting the API:

```bash
uv run python -m scripts.export_openapi openapi.generated.json
diff -u openapi.json openapi.generated.json
```

Check compatibility against another schema with `oasdiff`:

```bash
oasdiff breaking openapi.previous.json openapi.generated.json --fail-on ERR
```

`src/api.py` is the source of truth for `/api/v1` route groups. The root health route is
also included in OpenAPI.

`/metrics` is intentionally excluded from OpenAPI.

To update the generated frontend client while both repositories are checked out next to
each other:

```bash
cd ../conserium_client
OPENAPI_SCHEMA=../conserium/openapi.json npm run generate:api
npm run typecheck
npm test
```
