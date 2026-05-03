# Cortex: Project Status, Architecture, and Roadmap

## 1. Project Overview

### What Cortex is

Cortex is a personal AI knowledge system.

The user should be able to save or upload:

- PDFs
- articles and generic URLs
- notes and raw text
- YouTube videos
- audio / voice messages
- screenshots and images

After ingestion, the user should be able to ask natural-language questions such as:

- "What did I read about Clean Architecture?"
- "Summarize my notes about startup development."
- "Which documents mention PostgreSQL and pgvector?"
- "Find my saved materials about finance."
- "What are the main ideas from this PDF?"

The system should answer with:

- grounded answers
- source references
- citations
- document metadata
- streaming output similar to ChatGPT

### The problem Cortex solves

Most people already have a large personal knowledge base, but it is fragmented:

- browser bookmarks
- PDFs
- notes
- saved articles
- screenshots
- voice notes
- study and work materials

That information is usually difficult to retrieve later because search is weak, context is lost, and the content is spread across multiple tools. Cortex is intended to turn that archive into a searchable AI memory.

### Product direction

This project is not meant to stop at a basic RAG pipeline.

The target architecture is a **REFRAG-oriented personal memory system**:

- hybrid retrieval
- context compression
- citation-preserving synthesis
- streaming responses
- multi-step query orchestration
- asynchronous ingestion for heterogeneous content types


## 2. Current Stage

Current stage: **late Foundation / early Intelligence MVP**

This is no longer a skeleton project. The backend already has:

- working auth
- working document ingestion queueing
- working document status polling
- working query endpoints
- working SSE streaming
- working hybrid retrieval
- working REFRAG context packaging
- working LangGraph-backed query flow

At the same time, several intelligence and observability features are still not finished:

- OCR/image ingestion
- NER/classification/deduplication
- reranking
- eval/tracing stack
- full frontend


## 3. Current Implementation Status

### Implemented and working now

#### Foundation

- Clean Architecture package structure
- FastAPI application skeleton
- Dishka dependency injection
- SQLAlchemy async database setup
- PostgreSQL + pgvector schema
- Redis integration
- JWT auth with refresh-token rotation
- Google OAuth2 configuration placeholders
- GitHub OAuth2 configuration placeholders
- password hashing
- structured logging
- startup validation
- Docker and worker topology

#### Domain layer

- `UserEntity`
- `DocumentEntity`
- `ChunkEntity`
- document status and type value objects
- email value object
- domain exceptions

#### Persistence

- SQLAlchemy models for users, documents, chunks, collections, tags, and search history
- repositories for users, documents, and chunks
- unit of work
- pgvector search support
- HNSW vector indexes in schema

#### Ingestion

- async document ingestion entrypoint
- status caching in Redis
- background processing with Celery
- separate queues:
  - `document_processing`
  - `embeddings`
  - `hf_processing`
  - `notifications`
  - `cleanup`
- local file storage
- text chunking

#### Supported ingestion types right now

- `TEXT`
- `MARKDOWN`
- `URL`
- `PDF`
- `YOUTUBE`
- `AUDIO`

#### Content extraction implemented

- URL extraction via `trafilatura`
- PDF extraction via `pdfplumber`
- YouTube transcript extraction
- audio transcription through a separate HF worker using Whisper via `transformers`

#### Query pipeline

- sync query endpoint
- streaming query endpoint over SSE
- hybrid retrieval service
- vector search + PostgreSQL full-text search style fusion
- REFRAG context packaging
- citation-aware response structure
- conversation state persisted in Redis
- LangGraph-backed query graph

#### Observability

- basic `/metrics` endpoint
- latency metrics
- shared metrics storage via Redis
- queue depth rendering

#### Tests

Recent validated state:

- `150 passed`
- `2 skipped`

Coverage includes:

- domain entities
- auth use cases and routes
- ingestion use cases and routes
- extractors
- embedding provider behavior
- Celery task adapters
- query agents and graph runners
- REFRAG context builder
- SSE formatting
- conversation store


## 4. Current API Surface

### Health and metrics

- `GET /`
- `GET /metrics`

### Auth

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`

### Planned auth expansion

The project should also support OAuth2 login providers:

- Google
- GitHub

The backend config already includes provider-related settings, but the OAuth2 login flow is not implemented yet. This should become part of the auth roadmap and frontend auth UX.

### User

- `GET /api/v1/users/me`

### Documents

- `POST /api/v1/documents`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{document_id}`
- `DELETE /api/v1/documents/{document_id}`

### Ingestion

- `POST /api/v1/ingest`
- `POST /api/v1/ingest/pdf`
- `POST /api/v1/ingest/audio`
- `GET /api/v1/documents/{document_id}/status`

Compatibility aliases also exist for older ingestion routes.

### Query

- `POST /api/v1/query`
- `POST /api/v1/query/stream`


## 5. Architecture Overview

### Layered architecture

Dependency direction:

- `presentation -> application -> domain`
- `infrastructure -> application`
- `infrastructure -> domain`

The domain layer stays pure and does not depend on:

- FastAPI
- SQLAlchemy
- Redis
- Celery
- LangGraph
- OpenAI
- HuggingFace

### Package structure

```text
src/
  presentation/
    api/v1/
    schemas/
    dependencies/
    sse.py

  application/
    ports/
    dtos/
    use_cases/
    services/
    agents/

  domain/
    entities/
    value_objects/
    exceptions.py

  infrastructure/
    ai/
    auth/
    cache/
    celery/
    database/
    storage/
    text_processing/

  core/
    config.py
    container.py
    providers/
    logging.py
    metrics.py
    startup_checks.py
```

### Architecture by responsibility

#### Presentation

Responsible for:

- HTTP routing
- request/response schemas
- auth dependency handling
- SSE formatting
- mapping HTTP calls to application use cases

#### Application

Responsible for:

- use cases
- DTOs
- ports/interfaces
- retrieval orchestration
- REFRAG packaging
- LangGraph query flow
- conversation handling

#### Domain

Responsible for:

- business invariants
- entities
- value objects
- domain exceptions

#### Infrastructure

Responsible for:

- database implementation
- Redis implementation
- Celery implementation
- OpenAI providers
- content extractors
- file storage
- chunking implementation
- auth implementation


## 6. Query Architecture

The query side is already more advanced than a simple "retrieve chunks and dump them into the LLM" flow.

### Current query flow

1. Request hits `POST /api/v1/query` or `/api/v1/query/stream`
2. Query use case loads recent conversation turns from Redis
3. LangGraph query graph runs
4. Conversation context agent decides whether this is a follow-up
5. Router agent classifies the request
6. Retrieval agent runs hybrid retrieval
7. REFRAG context agent builds context package
8. Synthesis agent generates answer
9. Response includes sources and REFRAG metadata
10. Completed turn is stored back into conversation history

### Current agents/components

- `ConversationContextAgent`
- `RouterAgent`
- `RetrievalAgent`
- `RefragContextAgent`
- `SynthesisAgent`
- streaming synthesis variant
- LangGraph runners for sync and streaming modes

### Current retrieval behavior

- vector search through pgvector
- PostgreSQL keyword/full-text style retrieval
- fused ranking
- citation-ready source DTOs

### Current REFRAG behavior

The project already has a first heuristic REFRAG layer.

Supported representations:

- `FULL_TEXT`
- `COMPRESSED`
- `DISCARDED`

Current policy is heuristic:

- strongest chunks become full text
- medium-score chunks become compressed text
- weak chunks are discarded

This is still an MVP REFRAG policy, not the final relevance policy.


## 7. Ingestion Architecture

### Current ingestion flow

1. API accepts request
2. document is created and marked queued
3. Redis status is created
4. Celery task is dispatched
5. content is extracted
6. text is chunked
7. embeddings are generated in the embeddings queue
8. chunks are stored
9. document becomes `READY`

### Worker split

#### `worker-default`

Queues:

- `document_processing`
- `notifications`
- `cleanup`

Responsibilities:

- generic document processing
- extraction orchestration
- dispatch to downstream queues

#### `worker-embeddings`

Queue:

- `embeddings`

Responsibilities:

- OpenAI embeddings
- embedding cache usage
- final chunk persistence
- document finalization

#### `worker-hf`

Queue:

- `hf_processing`

Responsibilities:

- Whisper audio transcription
- future OCR / image / NER / classification tasks

This separation is correct and should be preserved as the project grows.


## 8. Security and Reliability Status

### Already improved

- startup fails when OpenAI embedding dimensions are invalid
- startup fails when `OPENAI_API_KEY` is missing outside debug
- URL ingestion has SSRF hardening
- redirects are validated manually
- standalone queries no longer inherit previous-source promotion incorrectly
- Celery task business logic has been pushed into application use cases

### Still important to keep improving

- stricter DNS rebinding defenses for remote URL ingestion
- dead-letter queue strategy
- per-step retry policy by task type
- richer ingestion failure diagnostics
- production-grade metrics aggregation and dashboards


## 9. What Is Done vs. What Is Not Done

### Done now

- auth system
- document CRUD basics
- text ingestion
- URL ingestion
- PDF ingestion
- YouTube ingestion
- audio ingestion via HF worker
- document status polling
- embeddings with cache
- hybrid retrieval
- REFRAG packaging
- sync query
- streaming query
- conversation state
- basic metrics
- Dockerized worker separation
- image ingestion
- OCR ingestion
- visual understanding for diagrams/screenshots (basic visual metadata (edge density, diagram_type, width/height) is computed and returned in ExtractedContent.visual, but advanced diagram reasoning (structure extraction, arrow/box detection, semantic interpretation) is not implemented yet).
- Google OAuth2 login
- GitHub OAuth2 login
- - NER tagging
- text classification
- deduplication
- reranker

### Not done yet

- EvalAgent
- RAGAS harness
  - deterministic local scorer is available by default for CI
  - external `ragas` integration is available with `EVAL_SCORER=ragas` and the `eval` optional dependency group
- Langfuse tracing
- Grafana dashboards
- GitHub Actions eval regression
- polished public API docs
- final frontend


## 10. What To Implement Next

This is the recommended order from the current state.


### Step 4: Eval and tracing

Implement:

- Langfuse tracing
- RAGAS evaluation harness
- baseline evaluation dataset
- CI regression checks

This is important before retrieval/compression policies get more sophisticated.

### Step 5: stronger frontend-client integration

Once ingestion and query intelligence are mature enough, frontend work becomes higher leverage.


## 11. Long-Term Goals

The final product goal is not just "search over saved chunks."

The final Cortex system should provide:

- asynchronous multimodal ingestion
- stable personal knowledge archive
- grounded answers with citations
- streaming query UX
- memory across conversations
- REFRAG-style context optimization
- retrieval quality evaluation
- observability around cost, latency, and answer quality

### Final-state capabilities

Target capabilities still ahead:

- YouTube with timestamp-aware citations
- OCR and visual ingestion
- image/screenshot understanding beyond OCR
- NER and topic tagging
- auto classification
- duplicate handling
- better retrieval with reranking
- answer evaluation and regression testing
- full tracing and dashboarding


## 12. What the Frontend Needs to Support

The frontend should be designed around the backend that already exists, not around a generic CRUD app.

### Core frontend capabilities required

#### Authentication

- register
- login
- refresh token handling
- login with Google
- login with GitHub
- protected routes
- logout/session reset

For OAuth2 support, the frontend should also handle:

- provider login buttons
- OAuth callback route/pages
- token/session handoff after provider auth completes
- linking the returned authenticated session to the same app state used for JWT login

#### Ingestion UX

- upload PDF
- upload audio
- submit raw text
- submit URL
- submit YouTube URL
- show queued/processing/ready/failed status
- poll `GET /documents/{id}/status`
- show errors from failed ingestion clearly

#### Document library

- document list view
- document detail view
- filters by type/status/collection later
- delete action
- show metadata:
  - title
  - source type
  - language
  - word count
  - duplicate markers later

#### Query experience

- chat-style query screen
- sync query fallback
- streaming query using SSE
- show citations
- show source document title and page number
- show REFRAG details in a debug/inspect panel
- preserve `conversation_id` across turns

#### Source inspection

- expandable source cards
- citation jump behavior
- page-aware PDF source display later
- transcript/source context preview

#### Observability/debug surface for development

For internal/dev UI, it is useful to expose:

- ingestion job status history
- query debug panel
- returned REFRAG package
- source scores
- queue/worker health summary


## 13. Recommended Frontend Stack

### Recommended default stack

Use:

- **Next.js**
- **TypeScript**
- **React**
- **TanStack Query**
- **Zustand**
- **Tailwind CSS**
- **shadcn/ui**

### Why this stack fits Cortex

#### Next.js

Good fit for:

- authenticated app shell
- route structure
- SSR where useful
- OAuth callback handling
- production-ready deployment model

#### TypeScript

Necessary for:

- strict API typing
- streaming event typing
- stable DTO mapping
- reducing frontend/backend contract drift

#### TanStack Query

Useful for:

- document lists
- document detail fetches
- auth-related server state
- ingestion polling
- retry handling
- cache invalidation after ingest/delete

#### Zustand

Useful for:

- local chat session state
- current `conversation_id`
- selected source panels
- transient UI state that does not belong in server cache

#### Tailwind CSS + shadcn/ui

Good fit for:

- fast implementation of a dense product UI
- practical component primitives
- non-marketing, application-style layout

### Streaming implementation recommendation

For `/api/v1/query/stream`, use:

- `EventSource` if request shape is compatible with your auth strategy
- otherwise `fetch()` + streamed response parser if bearer-token handling or richer request control is needed

Because the backend already emits structured SSE events, the frontend should model distinct event handlers for:

- `metadata`
- `token`
- `sources`
- `refrag_context`
- `done`
- `error`


## 14. Suggested Frontend Screens

At minimum, the frontend should have:

1. Auth screen
2. Document library screen
3. Ingestion screen/modal
4. Document detail screen
5. Query/chat screen
6. Source inspection panel

### Best initial UX shape

Recommended first usable product shape:

- left sidebar: navigation + saved conversations
- main area: chat/query interface
- right panel: citations, source previews, REFRAG debug
- top bar: upload / ingest actions

This maps well to the backend’s current capabilities.


## 15. Suggested Near-Term Backend Roadmap

### Phase A: complete multimodal ingestion MVP

- image upload route
- OCR extractor
- image processing use case
- HF task adapter for image/OCR

### Phase B: enrich documents during ingestion

- NER
- classification
- deduplication

### Phase C: improve retrieval quality

- reranker
- better context selection rules
- document-aware source weighting

### Phase D: evaluation and tracing

- Langfuse
- RAGAS
- regression suite
- dashboards

### Phase E: auth expansion

- Google OAuth2 login flow
- GitHub OAuth2 login flow
- provider account mapping/linking
- frontend OAuth callback handling
- unified session behavior across password and OAuth login


## 16. Summary

Cortex currently has a strong backend foundation and a real MVP query/ingestion pipeline.

It already supports:

- authenticated users
- document ingestion with background workers
- multiple document types
- query answering with citations
- REFRAG-style context packaging
- conversation-aware streaming responses

The project is now in the stage where the highest-value work is:

1. finish multimodal ingestion
2. enrich the knowledge base during ingestion
3. improve retrieval quality
4. add answer-quality evaluation and tracing
5. build the frontend product around the current backend contract

This is a good point to begin frontend implementation in parallel with the next backend intelligence slices.
