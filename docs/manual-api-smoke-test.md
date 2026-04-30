# Manual API Smoke Test

This is the minimal curl flow for manually checking the current Cortex MVP before adding LangGraph.

Assumptions:

- API is running at `http://localhost:8000`.
- PostgreSQL, Redis, RabbitMQ, `worker-default`, and `worker-embeddings` are running.
- `OPENAI_API_KEY` is configured for embedding/query paths.
- `jq` is installed locally.

Set shell variables:

```bash
export API_URL="http://localhost:8000"
export TEST_EMAIL="smoke-$(date +%s)@example.com"
export TEST_PASSWORD="ChangeMe123!"
```

## 1. Health Check

```bash
curl -sS "$API_URL/" | jq
```

Expected:

```json
{
  "status": "OK"
}
```

## 2. Register

```bash
curl -sS -X POST "$API_URL/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\",
    \"display_name\": \"Smoke Test User\"
  }" | tee /tmp/cortex-register.json | jq
```

Store the token:

```bash
export ACCESS_TOKEN="$(jq -r '.access_token' /tmp/cortex-register.json)"
export REFRESH_TOKEN="$(jq -r '.refresh_token' /tmp/cortex-register.json)"
```

## 3. Login

```bash
curl -sS -X POST "$API_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\"
  }" | tee /tmp/cortex-login.json | jq
```

Use the fresh login token:

```bash
export ACCESS_TOKEN="$(jq -r '.access_token' /tmp/cortex-login.json)"
```

## 4. Ingest Text

```bash
curl -sS -X POST "$API_URL/api/v1/ingest" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Clean Architecture Smoke Note",
    "type": "TEXT",
    "raw_content": "Clean Architecture keeps dependency direction pointing inward. The domain layer should not import FastAPI, SQLAlchemy, Redis, Celery, or OpenAI. Application services coordinate use cases through ports.",
    "language": "en"
  }' | tee /tmp/cortex-text-document.json | jq
```

Store the document id:

```bash
export TEXT_DOCUMENT_ID="$(jq -r '.id' /tmp/cortex-text-document.json)"
```

Expected document status in the response:

```json
"QUEUED"
```

## 5. Ingest URL

```bash
curl -sS -X POST "$API_URL/api/v1/ingest" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Example URL Smoke Document",
    "type": "URL",
    "source_url": "https://example.com",
    "language": "en"
  }' | tee /tmp/cortex-url-document.json | jq
```

Store the document id:

```bash
export URL_DOCUMENT_ID="$(jq -r '.id' /tmp/cortex-url-document.json)"
```

## 6. Poll Status

Poll the text document until it reaches `READY` or `FAILED`:

```bash
while true; do
  curl -sS "$API_URL/api/v1/documents/$TEXT_DOCUMENT_ID/status" \
    -H "Authorization: Bearer $ACCESS_TOKEN" | tee /tmp/cortex-text-status.json | jq

  STATUS="$(jq -r '.status' /tmp/cortex-text-status.json)"
  if [ "$STATUS" = "READY" ] || [ "$STATUS" = "FAILED" ]; then
    break
  fi

  sleep 2
done
```

Poll the URL document:

```bash
while true; do
  curl -sS "$API_URL/api/v1/documents/$URL_DOCUMENT_ID/status" \
    -H "Authorization: Bearer $ACCESS_TOKEN" | tee /tmp/cortex-url-status.json | jq

  STATUS="$(jq -r '.status' /tmp/cortex-url-status.json)"
  if [ "$STATUS" = "READY" ] || [ "$STATUS" = "FAILED" ]; then
    break
  fi

  sleep 2
done
```

Expected final successful status:

```json
{
  "status": "READY",
  "progress": 100
}
```

## 7. Query

Run this after at least one ingested document is `READY`:

```bash
curl -sS -X POST "$API_URL/api/v1/query" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What does my saved content say about Clean Architecture dependencies?",
    "limit": 5
  }' | tee /tmp/cortex-query.json | jq
```

Check the important response fields:

```bash
jq '{
  answer,
  sources,
  refrag_context: {
    full_text_chunks: .refrag_context.full_text_chunks,
    compressed_chunks: .refrag_context.compressed_chunks,
    total_original_tokens: .refrag_context.total_original_tokens,
    total_context_tokens: .refrag_context.total_context_tokens,
    compression_strategy: .refrag_context.compression_strategy
  }
}' /tmp/cortex-query.json
```

Expected behavior:

- `answer` is present.
- `sources` contains citations such as `[1]`.
- `refrag_context.full_text_chunks` is present.
- `compression_strategy` is `heuristic_v1_top3_score_threshold_sentence_compression`.

## 8. Useful Debug Commands

Check documents:

```bash
curl -sS "$API_URL/api/v1/documents?limit=20&offset=0" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

Check the latest status payload directly in Redis:

```bash
docker exec cortex_redis redis-cli GET "doc:status:$TEXT_DOCUMENT_ID"
```

Check workers:

```bash
docker compose ps
docker compose logs worker-default --tail=100
docker compose logs worker-embeddings --tail=100
```
