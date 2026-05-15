# Cortex — Senior Engineering Code Review (v4)

> **Backend**: Python 3.12 · FastAPI · Clean Architecture · Celery · PostgreSQL+pgvector · ~13,600 LOC + ~6,400 LOC tests (35 test files)
> **Frontend**: Next.js 16 · React 19 · TypeScript · Zustand · TanStack Query · Tailwind v4 · ~5,100 LOC



---

## I. Backend

### 1. Architecture — A−

Dependency flow `Presentation → Application → Domain ← Infrastructure` is properly enforced. No violations found.

**Strengths:**
- [IUnitOfWork](file:///Users/maksympushkash/cortex/src/application/ports/persistence/unit_of_work.py) — 7 declared repo attributes, docstring documents explicit-commit semantics
- [SQLAlchemyUnitOfWork](file:///Users/maksympushkash/cortex/src/infrastructure/database/unit_of_work.py) — Clean implementation, rollback-on-exception only, no auto-commit
- [startup_checks.py](file:///Users/maksympushkash/cortex/src/core/startup_checks.py) — Fail-fast validation of embedding dimensions, API keys, storage config
- [exception_handlers.py](file:///Users/maksympushkash/cortex/src/presentation/exception_handlers.py) — MRO traversal for status code mapping is elegant
- [oauth_redirects.py](file:///Users/maksympushkash/cortex/src/presentation/oauth_redirects.py) — Proper X-Forwarded-Proto/Host handling for reverse proxy, HttpOnly+SameSite cookies
- [sse.py](file:///Users/maksympushkash/cortex/src/presentation/sse.py) — 9 lines, does one thing perfectly
- [logging.py](file:///Users/maksympushkash/cortex/src/core/logging.py) — structlog with JSON prod / console dev, noisy loggers silenced

**Concerns:**

| Issue | Severity | Details |
|-------|----------|---------|
| **`core/` as composition root** | Medium | `core/providers/` imports from `infrastructure.*`. Should be `composition/` for clarity. |
| **`QueryOrchestrationService` has 5 UoW blocks** | Medium | [query_orchestration.py](file:///Users/maksympushkash/cortex/src/application/services/query_orchestration.py) — `prepare_context`, `record_query`, `record_chat_messages`, `ensure_chat_session`, `get_persisted_recent_turns` each open separate `async with self._uow:`. Highest UoW fragmentation in the codebase. If `record_query` commits but `record_chat_messages` fails, you get partial state. |
| **Manual Celery DI** | Medium | [composition.py](file:///Users/maksympushkash/cortex/src/infrastructure/celery/composition.py) — 4 functions manually constructing dependencies (135 lines). Adding a new dependency to any use case requires updating this file separately. |

---

### 2. Domain — A

- [DocumentEntity](file:///Users/maksympushkash/cortex/src/domain/entities/document_entity.py) — 395 lines, 20 params, rich invariants, defensive copies. `EMBEDDING_DIMENSIONS` sourced from `domain/constants.py`.
- [DocumentType](file:///Users/maksympushkash/cortex/src/domain/value_objects/document_type.py) — Clean `StrEnum` with 6 types including `MARKDOWN` for notes.
- [exceptions.py](file:///Users/maksympushkash/cortex/src/domain/exceptions.py) — Clean hierarchy: `DomainException` → `ValidationException`, `ResourceNotFoundException`, `ApplicationStateException` + specific subclasses. `OAuthAuthenticationException` carries an error `code` — good for OAuth error flows.

**Remaining concern:** 20-param constructor. Consider value objects: `FileInfo(path, size_bytes)`, `EnrichmentData(entities, categories, tags, suggested_questions)`.

---

### 3. Application Layer — A−

#### Query Pipeline (deep review)

The agent pipeline is well-separated:

| Agent | Lines | Responsibility | Quality |
|-------|-------|---------------|---------|
| [RouterAgent](file:///Users/maksympushkash/cortex/src/application/agents/query/router_agent.py) | 14 | Classify query type | ⚠️ Naive keyword matching (see below) |
| [ConversationContextAgent](file:///Users/maksympushkash/cortex/src/application/agents/query/conversation_context_agent.py) | 104 | Follow-up detection, query expansion | ✅ Clean with bilingual markers |
| [RetrievalAgent](file:///Users/maksympushkash/cortex/src/application/agents/query/retrieval_agent.py) | 85 | Hybrid search + rerank + quality filter | ✅ Well-structured pipeline |
| [RefragContextAgent](file:///Users/maksympushkash/cortex/src/application/agents/query/refrag_context_agent.py) | 15 | Build context package | ✅ Thin delegation |
| [SynthesisAgent](file:///Users/maksympushkash/cortex/src/application/agents/query/synthesis_agent.py) | 17 | LLM answer generation | ✅ Minimal, validates precondition |
| [EvalAgent](file:///Users/maksympushkash/cortex/src/application/agents/query/eval_agent.py) | 48 | RAGAS scoring + tracing | ✅ Graceful degradation on failure |

**New findings:**

| Issue | Severity | Details |
|-------|----------|---------|
| **RouterAgent is brittle** | Medium | Keyword matching (`"summarize"`, `"summary"`, `"pdf"`) for query classification. Ukrainian markers are a nice touch, but this will misclassify queries like "What is a summary of ML approaches?" (would match SUMMARY when it's really SEARCH). Consider LLM-based classification or at least word-boundary matching. |
| **`ConversationContextAgent` follow-up detection** | Low | `_looks_like_follow_up` checks if the query starts with pronouns/markers. Works for simple cases but misses: "Tell me more about the architecture" (no prefix match). False positive: "It Infrastructure Guide" (starts with "it"). |
| **`RetrievalAgent` creates filters inline** | Low | `ChunkQualityFilter()` and `ChunkRelevanceFilter()` are instantiated in `__init__` defaults. These are stateless — fine — but the `ChunkRelevanceFilter` is wired here but *also* could have been injected via the DI container for consistency. |

#### Query Use Cases

| File | Lines | Quality |
|------|-------|---------|
| [QueryUseCase](file:///Users/maksympushkash/cortex/src/application/use_cases/query/query_use_case.py) | 100 | ✅ Clean: validate → prepare → run graph → mark sources → persist → return |
| [StreamQueryUseCase](file:///Users/maksympushkash/cortex/src/application/use_cases/query/stream_query_use_case.py) | 210 | ⚠️ `__call__` is ~150 lines with inline dict construction for SSE events |

**StreamQueryUseCase concern:** Lines 72-148 construct 4 separate SSE event dicts with inline source/chunk serialization. The sync `QueryUseCase` uses `query_debug()` and `refrag_context_payload()` helpers from `query_orchestration.py`, but the stream version duplicates the serialization inline with slightly different field names (`"citation": f"[{index}]"` appears in 3 places). Extract a shared `source_to_stream_payload()` helper.

#### Note Use Cases

[note_use_cases.py](file:///Users/maksympushkash/cortex/src/application/use_cases/documents/note_use_cases.py) — 425 lines, **7 use case classes** + 10 private helpers. The version coalescing logic (`NOTE_VERSION_COALESCE_WINDOW = 60s`) is smart. The `_save_note_version` checks latest version timestamp before creating a new one.

**Issues (unchanged from v3):**

| Issue | Severity |
|-------|----------|
| 7 classes in 1 file (breaks project convention) | Medium |
| `_copy_document()` manually copies 21 fields | Medium |
| `_queue_note_processing` duplicates `queue_document_processing` | Low |
| No unit tests for any note use case | High |

#### Services

- [QueryOrchestrationService](file:///Users/maksympushkash/cortex/src/application/services/query_orchestration.py) — 231 lines. `mark_sources_used_in_answer()` parses `[N]` citations from answer text via regex. Clean. `title_from_query()` takes first 8 words, caps at 120 chars. `sources_payload()` is defined but only used via `query_debug_payload()` — minor dead-code smell.
- [EnrichmentService](file:///Users/maksympushkash/cortex/src/application/services/enrichment/enrichment_service.py) — Good composition of sub-services. Optional NER/classifier (graceful in dev without HuggingFace models).
- [ChunkQualityFilter](file:///Users/maksympushkash/cortex/src/application/services/retrieval/chunk_quality_filter.py) — Well-defined heuristics with explicit thresholds and garbage phrase detection.

#### Ports

All 11 port directories are clean abstract interfaces. `ILLMService` and `IStreamingLLMService` are separate interfaces — correct, since sync and streaming have different return types (`str` vs `AsyncIterator[str]`).

#### DTOs

13 DTO files, all `@dataclass(frozen=True, slots=True)`. `CortexQueryState` is `@dataclass(slots=True)` (mutable) — correct since agents mutate state through the pipeline. The `coerce_cortex_query_state()` function uses `cast()` heavily — this is a LangGraph compatibility shim for when state comes as a `Mapping`.

#### DI Providers

[QueryProvider](file:///Users/maksympushkash/cortex/src/core/providers/query.py) — 122 lines, 9 factory methods. Clean. The reranker factory has a `fallback` pattern (CrossEncoder falls back to EmbeddingReranker). Same for eval scorer (RAGAS falls back to heuristic). Good degradation design.

---

### 4. Infrastructure — B+

- Celery Dockerfile installs `tesseract-ocr-ukr` for Ukrainian OCR — good i18n
- `__init__.py` for tasks only exports 2 tasks in `__all__` — clean public API
- `composition.py` properly closes Redis connections in `finally` blocks

**Unchanged concerns:** Manual DI in workers, custom metrics registry.

---

### 5. Presentation — A

- [notes.py](file:///Users/maksympushkash/cortex/src/presentation/api/v1/notes.py) — 113 lines, 7 endpoints. Clean: auth → map → use case → map → response. Proper HTTP semantics (201 for create, 204 for delete).
- [query.py](file:///Users/maksympushkash/cortex/src/presentation/api/v1/query.py) — 55 lines. Uses `query_latency_timer` context manager for metrics.
- All routes use Dishka `@inject` + `FromDishka[...]` for DI. Consistent pattern.

---

### 6. Testing — B+

35 unit test files, ~6,400 LOC. Strong coverage of:
- Domain entities, auth use cases, document use cases, query agents, embedding provider
- Eval scoring, REFRAG context building, reranker, extractors, SSE formatting
- Celery dependency validation, error handling, task dispatch

**Gaps:**
- No tests for `note_use_cases.py` (425 lines of logic)
- No tests for `QueryOrchestrationService` (231 lines)
- No integration tests for the full query pipeline

---

## II. Frontend

### 1. Architecture — B+

```
src/
├── app/          9 routes (chat, documents, notes, ingest, collections, etc.)
├── components/   chat/(7), documents/(4), notes/(3+tests), ui/(6), + 4 shared
├── hooks/        4 hooks + 2 test files
├── lib/api/      9 domain modules + transport core
├── stores/       3 Zustand stores (auth, chat, ui)
└── test/         setup.ts
```

**What's excellent:**
- Chat page decomposed: 572 → 154 lines ✅
- Documents page decomposed: 300+ → 140 lines ✅
- API client split: 1 monolith → 9 modules ✅
- Session management with cross-tab sync ✅
- Error boundaries + skeleton loading ✅

### 2. New Finding: Notes Page Is a Monolith — ⚠️ HIGH

[notes/page.tsx](file:///Users/maksympushkash/client/src/app/notes/page.tsx) is **545 lines** — the **largest file in the frontend**. This is the exact same problem that was fixed in chat and documents pages. It contains:

- 10 `useState` hooks
- 5 TanStack Query hooks
- 5 mutations
- 6 `useEffect` blocks
- Slash command palette logic (type definitions, command list, filtering)
- Autosave logic with coalescing
- Image upload handling
- Editor mode toggle (edit/preview)
- Inline rendering for header, editor, slash menu, empty state

**Recommended decomposition:**
- `NoteEditor` (textarea, title input, slash menu)
- `NoteSlashMenu` (command palette overlay)
- `useNoteEditor` hook (autosave, content state, slash commands)
- `useNoteImageUpload` hook (file input, mutation)

### 3. Document Detail Page — Medium concern

[documents/[id]/page.tsx](file:///Users/maksympushkash/client/src/app/documents/%5Bid%5D/page.tsx) is **403 lines** with 8 inline helper components (`HighlightedContent`, `DialogPanel`, `ProcessingTimeline`, `TimelineStep`, `Row`, `SuggestedQuestions`, `TagBlock`, `JsonBlock`). These should be extracted to `components/documents/` for reuse and testability.

### 4. Hooks — A−

All 4 hooks are well-structured. `useChatQueryStream` (140 lines) handles both sync/streaming modes with `AbortController`. `useUndoableDocumentDelete` properly cleans up timeouts on unmount.

**No tests for `useChatQueryStream`** — the most complex hook. Priority test target.

### 5. API Client — A−

Transport layer is clean. Domain modules are focused (each under 100 lines).

**Issues:**

| Issue | Severity | Details |
|-------|----------|---------|
| **`streamQueryDocuments` no 401 retry** | Medium | [query.ts](file:///Users/maksympushkash/client/src/lib/api/query.ts#L27-L84) calls `fetch` directly, bypassing the `request()` function's 401 retry logic. If the access token expires mid-stream, it throws. |
| **`undefined as T` for 204** | Low | [transport.ts L92](file:///Users/maksympushkash/client/src/lib/api/transport.ts#L92) — type-unsafe cast. Consider a `requestVoid()` overload. |
| **Alias exports in auth.ts** | Low | `fetchMe = getCurrentUser`, `logoutAll = logoutEverywhere`, `deleteAccount = deleteCurrentUser` — unnecessary indirection. Pick one name. |

### 6. Stores — A−

- [auth-store.ts](file:///Users/maksympushkash/client/src/stores/auth-store.ts) — 29 lines. Clean Zustand + `persist` middleware. Custom `merge` function for rehydration safety.
- [chat-store.ts](file:///Users/maksympushkash/client/src/stores/chat-store.ts) — 44 lines. `updateMessage` uses immutable map pattern. `resetConversation` clears all state.

**Concern:** Chat store holds all messages in memory with no pagination. For long conversations this will grow unbounded.

### 7. CSS — B+

[globals.css](file:///Users/maksympushkash/client/src/app/globals.css) — Clean. `!important` override removed. `font-weight: 300` scoped to `body`. Custom `animate-soft-in` keyframe.

**Minor:** `::selection` uses black background + white text — this matches the dark theme but makes selection invisible on any text that's already white-on-black (which is most of the UI). Consider a contrasting selection color.

### 8. Testing — C+

3 tests total (2 hook tests, 1 component test). Vitest + Testing Library properly configured.

**Priority gaps:**
1. `useChatQueryStream` — streaming, abort, error handling
2. `useDocumentFilters` — multi-criteria filtering
3. API transport — 401 retry flow
4. Notes page — no tests at all for the most complex page

---

## III. Summary

| Dimension | Grade | Key finding |
|-----------|-------|-------------|
| Backend Architecture | A− | Clean Architecture properly enforced |
| Domain Model | A | Rich entities, shared constants, strong invariants |
| Query Pipeline | A− | Well-separated agents, good degradation. RouterAgent is naive. |
| Application Services | A− | Clean orchestration. StreamQueryUseCase has inline serialization. |
| Infrastructure | B+ | Manual Celery DI, custom metrics |
| Backend API | A | Thin routes, proper HTTP semantics |
| Backend Tests | B+ | 35 test files. Gap: note use cases, orchestration service |
| Frontend Architecture | B+ | Good decomposition except notes page |
| Frontend Components | B+ | notes/page.tsx (545 lines) and documents/[id] (403 lines) need work |
| Frontend Hooks | A− | 4 well-structured hooks. Need tests for useChatQueryStream |
| Frontend API Client | A− | Clean split. streamQueryDocuments skips 401 retry |
| Frontend Tests | C+ | 3 tests for ~5,100 LOC |
| Security | A− | OAuth CSRF, JWT rotation, HttpOnly cookies, proper CORS |
| Logging | A− | structlog, JSON prod, console dev |

### Top 5 Action Items (prioritized)

1. **Decompose `notes/page.tsx`** (545 lines) — Extract `NoteEditor`, `NoteSlashMenu`, `useNoteEditor`, `useNoteImageUpload`. Same pattern you used for chat/documents.

2. **Test `note_use_cases.py`** — Version coalescing, restore, empty content handling, concurrent saves. 425 lines of untested business logic.

3. **Split `note_use_cases.py`** into separate files — 7 classes violates your own convention.

4. **Fix `streamQueryDocuments` 401 handling** — Add token refresh before the fetch call, or wrap with retry logic.

5. **Extract `documents/[id]/page.tsx` helpers** — Move 8 inline components to `components/documents/` for reuse and testability.
