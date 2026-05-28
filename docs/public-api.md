# Conserium Public API

Default local API origin: `http://localhost:8000`

Versioned API base: `http://localhost:8000/api/v1`

Interactive OpenAPI docs:

- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`

Browser UI authentication uses bearer access tokens returned by register, login, refresh, or OAuth callbacks.

```http
Authorization: Bearer <access_token>
```

Developer and automation authentication uses Conserium API keys created in Settings → Integrations.

```http
Authorization: Bearer ctx_<api_key>
```

API keys are shown once at creation time. Store only the token prefix in user-facing logs.

## API Keys

`GET /api/v1/api-keys`

Lists API keys for the current user. The plaintext token is never returned.

`POST /api/v1/api-keys`

```json
{
  "name": "n8n webhook",
  "scopes": ["ingest:write"]
}
```

Returns:

```json
{
  "api_key": {
    "id": "...",
    "name": "n8n webhook",
    "prefix": "ctx_abc123...",
    "scopes": ["ingest:write"],
    "last_used_at": null,
    "revoked_at": null,
    "created_at": "2026-05-25T12:00:00Z"
  },
  "token": "ctx_full_token_shown_once"
}
```

`DELETE /api/v1/api-keys/{api_key_id}`

Revokes a key.

## External Intake

External intake is the normalized ingestion path for API keys, webhooks, browser extensions, Telegram, and automation tools.

Supported document types:

- `TEXT`
- `MARKDOWN`
- `URL`
- `YOUTUBE`

Shared payload fields:

```json
{
  "title": "Saved article",
  "type": "URL",
  "source_url": "https://example.com/article",
  "raw_content": null,
  "collection_id": null,
  "tags": ["research"],
  "language": "en",
  "provider": "webhook",
  "external_id": "zapier-run-123",
  "idempotency_key": "zapier-run-123",
  "metadata": {
    "source": "zapier"
  }
}
```

Use `idempotency_key` to prevent duplicate ingestion. If omitted, Conserium falls back to `external_id`, then URL hash for URL payloads.

`POST /api/v1/public-api/ingest`

API-key authenticated ingestion for scripts and first-party clients.

`POST /api/v1/webhooks/ingest`

API-key authenticated webhook endpoint for Zapier, Make, n8n, IFTTT, browser extensions, Telegram adapters, and custom automation.

Response:

```json
{
  "intake_item": {
    "id": "...",
    "provider": "webhook",
    "external_id": "zapier-run-123",
    "idempotency_key": "zapier-run-123",
    "title": "Saved article",
    "type": "URL",
    "collection_id": null,
    "tags": ["research"],
    "source_url": "https://example.com/article",
    "status": "QUEUED",
    "error_reason": null,
    "document_id": "...",
    "payload_metadata": {
      "source": "zapier",
      "tags": ["research"]
    },
    "created_at": "2026-05-25T12:00:00Z",
    "updated_at": null
  },
  "document": {
    "id": "...",
    "title": "Saved article",
    "status": "QUEUED"
  }
}
```

## Notion Import

Notion OAuth must be connected before import.

`GET /api/v1/integrations/notion/pages?query=architecture&limit=10`

Searches accessible Notion pages.

`POST /api/v1/integrations/notion/import`

```json
{
  "page_id": "notion-page-id",
  "collection_id": null,
  "tags": ["notion"]
}
```

Imports the page blocks as Markdown through external intake with provider `notion`.

## Browser Extension MVP

The browser extension scaffold is in `client/extensions/browser`.

Configuration fields:

- API origin: `https://api.conserium.app/api/v1`
- API key: a `ctx_...` key with `ingest:write`
- Collection id: optional
- Tags: comma-separated

The extension stores credentials in browser-local extension storage, loads collections from:

`GET /api/v1/public-api/collections`

It sends current-tab URLs and selected text to:

`POST /api/v1/public-api/ingest`

## Telegram Bot MVP

The Telegram adapter is in `scripts/telegram_webhook_bot.py`.

Run it separately:

```bash
CONSERIUM_API_BASE_URL=https://api.conserium.app/api/v1 \
CONSERIUM_TELEGRAM_SECRET=... \
TELEGRAM_BOT_TOKEN=... \
uvicorn scripts.telegram_webhook_bot:app --host 0.0.0.0 --port 8090
```

Set the Telegram webhook to:

```text
https://<bot-host>/telegram/webhook
```

Create a Telegram pairing code in Conserium Settings, then pair a Telegram chat by sending:

```text
/pair <code>
```

Forwarded URLs become `URL` or `YOUTUBE` documents. Plain text becomes a `TEXT` document. Telegram message id is used as the idempotency key. Chat bindings and revocation live in Conserium.

## Anytype Import MVP

Export Anytype notes as Markdown, then import them with:

```bash
CONSERIUM_API_BASE_URL=https://api.conserium.app/api/v1 \
CONSERIUM_API_KEY=ctx_... \
uv run python scripts/import_anytype_export.py /path/to/anytype/export
```

The script sends each Markdown file through:

`POST /api/v1/webhooks/ingest`

Use:

```json
{
  "provider": "anytype",
  "external_id": "anytype-object-id",
  "idempotency_key": "anytype-object-id",
  "title": "Anytype note",
  "type": "MARKDOWN",
  "raw_content": "# Note content",
  "tags": ["anytype"]
}
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

The OAuth start routes redirect to the provider. The callback routes validate the HTTP-only OAuth `state` cookie and return Conserium access/refresh tokens as JSON.

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

By default, Conserium uses a deterministic local scorer for CI and development. Set `EVAL_SCORER=ragas` and install the optional eval dependencies to use the external RAGAS library:

```bash
uv sync --extra eval
EVAL_SCORER=ragas uv run uvicorn src.main:app
```
