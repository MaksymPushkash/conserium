# Cortex Public API

Default local API origin: `http://localhost:8000`

Versioned API base: `http://localhost:8000/api/v1`

Interactive OpenAPI docs:

- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`

Authentication uses bearer access tokens returned by register, login, refresh, or OAuth callbacks.

```http
Authorization: Bearer <access_token>
```

## Health

`GET /health`

Returns a small service health payload.

`GET /`

Legacy alias for the same health payload.

`GET /metrics`

Returns Prometheus text output. This endpoint is intentionally not under `/api/v1` and is hidden from the OpenAPI schema.

Current metric families include:

- HTTP request counters
- ingestion latency
- query latency
- query eval scores
- embedding cache events
- OpenAI provider events
- reranker events
- RabbitMQ queue depth

## Auth

`POST /api/v1/auth/register`

```json
{
  "email": "user@example.com",
  "password": "secret-password",
  "display_name": "User"
}
```

Returns:

```json
{
  "access_token": "...",
  "refresh_token": "..."
}
```

`POST /api/v1/auth/login`

```json
{
  "email": "user@example.com",
  "password": "secret-password"
}
```

`POST /api/v1/auth/refresh`

```json
{
  "refresh_token": "..."
}
```

OAuth:

- `GET /api/v1/auth/google`
- `GET /api/v1/auth/google/callback`
- `GET /api/v1/auth/github`
- `GET /api/v1/auth/github/callback`

The OAuth start routes redirect to the provider. The callback routes validate the HTTP-only OAuth `state` cookie and return Cortex access/refresh tokens as JSON.

## Users

`GET /api/v1/users/me`

Returns the current authenticated user.

## Documents

`POST /api/v1/documents`

Creates a document record synchronously. This is useful for direct CRUD flows, but ingestion should normally use the async `/ingest` endpoints.

```json
{
  "title": "Saved note",
  "type": "TEXT",
  "raw_content": "Clean Architecture keeps dependencies inward.",
  "collection_id": null,
  "source_url": null,
  "file_path": null,
  "file_size_bytes": null,
  "summary": null,
  "word_count": null,
  "language": "en"
}
```

`GET /api/v1/documents?limit=50&offset=0`

Returns a lightweight list read model. List items intentionally exclude full `raw_content`.

`GET /api/v1/documents/{document_id}`

Returns one document with content and metadata:

- enrichment entities
- categories
- visual metadata
- tags
- duplicate state

`DELETE /api/v1/documents/{document_id}`

Deletes document metadata and stored file content.

## Ingestion

`POST /api/v1/ingest`

Queues text, markdown, URL, or YouTube ingestion and returns `202 Accepted`.

Text example:

```json
{
  "title": "Saved note",
  "type": "TEXT",
  "raw_content": "Clean Architecture keeps dependencies inward.",
  "collection_id": null,
  "language": "en"
}
```

URL example:

```json
{
  "title": "Article",
  "type": "URL",
  "source_url": "https://example.com/article"
}
```

YouTube example:

```json
{
  "title": "Talk",
  "type": "YOUTUBE",
  "source_url": "https://www.youtube.com/watch?v=..."
}
```

`POST /api/v1/ingest/pdf`

Multipart form fields:

- `file`: required upload
- `title`: optional
- `collection_id`: optional
- `language`: optional

`POST /api/v1/ingest/audio`

Multipart form fields:

- `file`: required upload
- `title`: optional
- `collection_id`: optional
- `language`: optional

Audio transcription runs through the `media_processing` worker.

`POST /api/v1/ingest/image`

Multipart form fields:

- `file`: required upload
- `title`: optional
- `collection_id`: optional
- `language`: optional

Image ingestion runs OCR and structural diagram extraction through the `media_processing` worker.

`GET /api/v1/documents/{document_id}/status`

Returns Redis-backed ingestion status:

```json
{
  "document_id": "...",
  "status": "PROCESSING",
  "progress": 60,
  "message": "Queued for embedding..."
}
```

Deprecated ingestion aliases still exist for backward compatibility:

- `POST /api/v1/documents/ingest`
- `POST /api/v1/documents/ingest/pdf`
- `POST /api/v1/documents/ingest/audio`
- `POST /api/v1/documents/ingest/image`
- `POST /api/v1/documents/ingest-text`

New frontend work should use `/api/v1/ingest*`.

## Query

`POST /api/v1/query`

```json
{
  "query": "What did I read about Clean Architecture?",
  "conversation_id": null,
  "collection_id": null,
  "limit": 5
}
```

Returns:

- answer
- sources with citations
- REFRAG context package
- conversation id

`POST /api/v1/query/stream`

Same request body as `/query`.

Streams Server-Sent Events with media type `text/event-stream`.

Event names:

- `metadata`
- `token`
- `sources`
- `refrag_context`
- `done`
- `error`

The final `done` event includes `eval_scores` and `trace_id`.

## Evaluation

Offline regression harness:

```bash
uv run python scripts/run_eval_harness.py
```

Write a JSON report:

```bash
uv run python scripts/run_eval_harness.py --output artifacts/eval-regression-report.json
```

Against a running API:

```bash
uv run python scripts/run_eval_harness.py --base-url http://localhost:8000 --token "$ACCESS_TOKEN"
```

By default, Cortex uses a deterministic local scorer for CI and development. Set `EVAL_SCORER=ragas` and install the optional eval dependencies to use the external RAGAS library:

```bash
uv sync --extra eval
EVAL_SCORER=ragas uv run uvicorn src.main:app
```
