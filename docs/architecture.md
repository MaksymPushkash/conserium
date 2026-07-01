# Conserium Architecture

Conserium is a feature-first modular monolith.

## System Boundaries

```mermaid
flowchart LR
    WEB["Next.js frontend on Vercel"] --> API["FastAPI API on VPS"]
    API --> POSTGRES["PostgreSQL + pgvector"]
    API --> REDIS["Redis cache and Taskiq result backend"]
    API --> RABBITMQ["RabbitMQ Taskiq broker"]
    API --> STORAGE["S3 or local storage"]
    RABBITMQ --> WORKERS["Taskiq workers on VPS"]
    BEAT["Taskiq scheduler"] --> RABBITMQ
    WORKERS --> POSTGRES
    WORKERS --> STORAGE
```

The frontend and backend deploy independently. Deployment topology does not determine
repository topology.

## Backend Structure

```text
src/
├── main.py                # FastAPI application and lifespan
├── api.py                 # Central /api/v1 router registration
├── postgres.py            # Async engine and request transaction dependencies
├── routing.py             # Shared routing exports
├── exceptions.py          # HTTP exception translation
├── settings.py            # Environment-backed configuration
├── models/                # Shared SQLAlchemy models
├── kit/                   # Cross-cutting code only
├── worker/                # Taskiq broker, queues, registry, and shared worker helpers
└── {feature}/             # Feature-owned behavior
```

Primary feature packages include `documents`, `collections`, `workspaces`,
`public_shares`, `query`, `chats`, `review`, `topics`, `knowledge_graph`,
`knowledge_gaps`, `learning_goals`, `drafts`, `integrations`, `notifications`,
`repo_syncs`, `api_keys`, `users`, and `auth`.

## Feature Modules

A feature owns the files it needs:

- `endpoints.py`: HTTP parsing, dependency declarations, status codes, and response construction.
- `schemas.py`: Pydantic request, response, and feature data contracts.
- `service.py`: business rules and orchestration.
- `repository.py`: SQLAlchemy statements and persistence operations.
- `auth.py`: feature authorization dependencies.
- `tasks.py`: feature-owned Taskiq task entry points.
- `sorting.py`: sort definitions when the feature supports sorting.

These filenames are conventions, not a requirement to create empty files. Add a file only
when the feature owns that behavior.

Large features may split cohesive behavior into additional files such as
`documents/ingestion.py`, `documents/processing.py`, and `documents/notes.py`. Do not
recreate generic `application`, `domain`, `infrastructure`, `use_cases`, `dtos`, or
feature-local `ports` layers.

## Endpoint, Service, Repository Pattern

The normal backend flow is:

```python
# endpoints.py
@router.post("/", response_model=ResourceResponse, status_code=201)
async def create_resource(
    current_user: CurrentUser,
    body: ResourceCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    service: ResourceService = Depends(get_resource_service),
) -> ResourceResponse:
    return await service.create(session, user_id=current_user.id, body=body)
```

```python
# service.py
class ResourceService:
    async def create(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        body: ResourceCreateRequest,
    ) -> ResourceResponse:
        repository = ResourceRepository.from_session(session)
        resource = await repository.create(user_id=user_id, body=body)
        await session.flush()
        return ResourceResponse.model_validate(resource)
```

```python
# repository.py
class ResourceRepository(RepositoryBase[ResourceModel]):
    model = ResourceModel

    async def get_for_user(self, *, user_id: UUID, resource_id: UUID) -> ResourceModel | None:
        statement = select(ResourceModel).where(
            ResourceModel.id == resource_id,
            ResourceModel.user_id == user_id,
        )
        return await self.get_one_or_none(statement)
```

Rules:

1. Endpoints describe HTTP behavior. They do not contain SQLAlchemy, Redis clients, token ciphers,
   or external client construction.
2. Services are framework-independent. They do not import FastAPI and they do not construct
   `Depends`.
3. Services pass request schemas or explicit arguments directly. Do not add command, DTO, or mapper
   layers between endpoints and services.
4. Repositories own SQLAlchemy statements. Repository methods use `self.session`, inherited from
   `RepositoryBase.from_session(session)`.
5. Use concrete repositories when there is one production implementation. Keep abstract classes only
   for real external strategies such as storage, extraction, embeddings, LLMs, reranking, and eval
   scoring.

## Request Flow

```text
HTTP request
  -> feature endpoint
  -> feature service
  -> feature repository
  -> shared SQLAlchemy model
  -> response schema
```

Rules:

1. Endpoints stay thin and do not construct SQLAlchemy statements.
2. Services contain business decisions and compose feature behavior.
3. Repositories own database queries and persistence details.
4. Cross-feature calls use the owning feature's public service or repository API.
5. External systems use protocols only when substitution is real: AI, cache, storage,
   OAuth, tracing, notifications, and worker dispatch.

## Transactions

`src.postgres.get_db_session` owns the HTTP write transaction:

- commit after a successful request;
- rollback when request handling raises;
- close the session when the dependency exits.

New request-path services must not call `session.commit()`. Use `session.flush()` when a
generated value or constraint must be visible before the request ends.

Workers own their task transaction boundary. A worker may commit an explicit checkpoint
only when the task is deliberately resumable and the partial state is part of the task's
failure model. That decision belongs in worker or processing code, not ordinary HTTP
services.

Public-share abuse accounting commits its reservation before a rejected or expensive
external query so concurrent requests cannot bypass daily limits. This is an explicit
transaction boundary, not ordinary request persistence.

## Database Models and Repositories

SQLAlchemy models are shared in `src/models`.
Feature repositories import those models and expose concrete repository APIs.

Prefer direct concrete repositories when there is one implementation. Keep interfaces for
external adapters or genuinely interchangeable implementations, not for every SQLAlchemy
repository.

Document HTTP services receive the request `AsyncSession` and concrete repositories.
Repositories keep their session private; services use the request session directly when a
flush is required. Core document endpoints depend on one cohesive `DocumentService` rather
than an action-specific dependency per route.

## Background Jobs

Taskiq is the worker system.

- `src/worker/app.py` configures Taskiq, RabbitMQ broker URLs, Redis result backend, queues, routing, and scheduler.
- `src/worker/registry.py` lists feature task modules.
- `src/worker/task_names.py` defines stable producer-facing task names.
- Feature `tasks.py` files own task entry points and delegate to feature processing code.

Production processes:

| Process | Queues or responsibility |
|---|---|
| `worker-default` | `document_processing`, `notifications`, `cleanup` |
| `worker-embeddings` | `embeddings` |
| `worker-media` | `media_processing`, `hf_processing` |
| `scheduler` | Taskiq scheduler schedules |

RabbitMQ is the Taskiq broker, Redis database `1` is the result backend, and Redis
database `0` is application cache/state.

The HTTP application owns one cached Redis client in `src/kit/cache/redis.py`. Feature
cache adapters receive that shared client. Worker processes own separate Redis clients and
close them at the task boundary.

## Shared Code

`src/kit` is limited to code that has multiple feature consumers:

- base schemas, pagination, sorting, and repository helpers;
- AI, cache, storage, and security adapters;
- protocols for external systems with real alternate implementations;
- shared exceptions and constants.

Feature-specific records, repository composition, and business rules stay in the owning
feature package.

Do not move feature code into `src/kit` to avoid imports. Shared code must have multiple concrete
callers and no feature-specific policy.

## Frontend Contract

The frontend is maintained in the separate `conserium_client` repository and deployed to
Vercel. It uses `openapi-typescript` and `openapi-fetch`.

Contract flow:

1. Run `uv run python -m scripts.export_openapi openapi.json` in the backend.
2. Backend CI fails when the committed schema differs from the application schema.
3. Backend CI uses `oasdiff` to reject breaking changes against the pull request base branch.
4. Frontend CI regenerates `src/lib/api/generated/v1.ts` from backend `main` and fails on a
   diff.
5. Type-check and test the frontend.

Backend changes that intentionally alter the contract update `openapi.json`. The frontend
generated client and wrappers then update in the frontend repository before its deployment.

Manual frontend transport is limited to behavior that generated JSON clients do not model
well: login/refresh bootstrap, multipart uploads, binary downloads, and SSE.

## Deployment

Backend production runs on a VPS through Docker Compose:

- FastAPI application behind Nginx;
- PostgreSQL with pgvector;
- Redis;
- three Taskiq workers;
- Taskiq scheduler;
- Prometheus and Grafana.

The Next.js frontend deploys independently to Vercel and calls the public API origin.
CORS is controlled by `FRONTEND_URL`.

## Repository Decision

Conserium should remain in two repositories for now.

Conserium currently has one backend and one web application with independent deployments.
Moving files into a monorepo would add workspace and deployment complexity without removing
the main contract risk.

Reconsider a monorepo when at least one of these becomes true:

- a mobile or second web application needs shared TypeScript packages;
- a reusable UI package or public SDK becomes a product boundary;
- most product changes require atomic backend, generated-client, and frontend commits;
- one CI pipeline is needed to coordinate compatibility and releases.

The separate CI checks enforce the OpenAPI contract without requiring a monorepo.

## Architecture Decisions

Taskiq with RabbitMQ and two repositories are deliberate choices. They should not change unless product needs
change. The architecture risk is contract drift, not repository location.

## Current State

The removed layers are gone:

- no `src/application`;
- no `src/presentation`;
- no `src/core`;
- no `src/domain`;
- no `src/infrastructure`;
- no `src/dependencies.py`;
- no `src/kit/ports`;
- no global UOW;
- no feature-local `dtos`, `ports`, or `use_cases`.

The remaining abstract classes are external strategy boundaries with real provider substitution:

- `src/documents/extraction.py:ContentExtractor`
- `src/kit/storage/file_storage.py:FileStorage`
- `src/kit/ai/embedding_provider.py:EmbeddingProvider`
- `src/kit/ai/llm_service.py:LLMService`
- `src/kit/ai/llm_service.py:StreamingLLMService`
- `src/query/services/retrieval/reranker.py:Reranker`
- `src/query/services/evaluation/scorer.py:EvalScorer`

Do not add abstract repositories, feature-local ports, command interfaces, or test-only protocols.

## Architecture Checks

The architecture test suite prevents removed layers, Dishka, global UOW names, document
repository sessions, request-path commits, SQLAlchemy inside endpoints, empty convention
placeholders, and feature-local `dtos`, `ports`, or `use_cases` folders from returning.
It also enforces the exact approved abstract strategy set listed above.

Run:

```bash
uv run ruff check src tests scripts/run_eval_harness.py scripts/backfill_topics.py
uv run mypy src
uv run pytest tests -q
```

Architecture tests should enforce dependency direction and behavior. They should not force
empty convention files or rely only on banned class names.
