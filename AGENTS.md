

## General Guidelines

- Do not add comments to the code unless necessary. The code should be self-explanatory.
- Use meaningful variable and function names.
- Follow good practices and code conventions.
- Make sure that all new code is maintainable and follows the SOLID principles.
- Do not modify unrelated code to the task or issue you are working on.

## Architecture

Conserium is a feature-first modular monolith.

- Keep feature behavior under `src/{feature}`.
- Keep FastAPI handlers in `endpoints.py` thin.
- Keep business orchestration in feature service modules.
- Keep SQLAlchemy statements and persistence operations in repository modules.
- Keep shared SQLAlchemy models in `src/models`.
- Keep cross-cutting helpers and base classes in `src/kit`.
- Keep Taskiq configuration in `src/worker` and task entry points in feature `tasks.py` files.
- Use FastAPI dependencies. Do not introduce a dependency injection container.
- Do not recreate `application`, `presentation`, `domain`, `infrastructure`, `use_cases`, `dtos`, or feature-local `ports` layers.
- Do not create empty convention files. Add `auth.py`, `sorting.py`, or `tasks.py` only when the feature owns that behavior.
- Let the request or worker boundary own transactions. Request-path services must not call `session.commit()`.

See `docs/architecture.md` for the complete structure and enforced boundaries.

## Backend Conventions

Feature packages use only the files they need:

- `endpoints.py`: route declarations, request parsing, dependencies, response status codes.
- `schemas.py`: Pydantic API request and response schemas.
- `service.py`: business decisions and orchestration.
- `repository.py`: SQLAlchemy query and persistence logic.
- `auth.py`: feature-local authorization dependencies when needed.
- `tasks.py`: feature-owned Taskiq task entry points when needed.
- `sorting.py`: feature-local sort declarations when needed.

Do not add placeholder files to satisfy a layout convention.

### Repositories

- All SQLAlchemy statements belong in repository modules.
- Repositories are concrete classes. Do not add interfaces for a single SQLAlchemy implementation.
- Construct repositories from the request or worker session.
- Repository methods use domain arguments, not framework objects.
- Return updated models or explicit projection records.
- Use `flush()` when generated values or constraints must be visible before the boundary commits.

### Services

- Services contain business logic and call repositories.
- Services must not import FastAPI or construct `Depends`.
- Prefer passing `AsyncSession` into service methods, then constructing concrete repositories locally.
- Avoid request-to-command-to-service mapping. Pass Pydantic request schemas or explicit method arguments directly.
- Keep algorithms in cohesive files when a feature grows, for example `review/flashcards.py` or `documents/search.py`.
- Do not introduce action-per-route classes unless the behavior is a real reusable processor.

### Transactions

- HTTP write sessions commit in `src.postgres.get_db_session`.
- Read sessions do not commit.
- Worker helpers commit at task boundaries.
- Explicit commits are allowed only for documented ledger or checkpoint code.
- Ordinary request-path services use `flush()`, not `commit()`.

### Workers

- Add task names in `src/worker/task_names.py`.
- Register feature task modules in `src/worker/registry.py`.
- Implement task entry points in the owning feature package.
- Keep task bodies thin; delegate business work to feature processing code.

### API Contracts

- Backend `openapi.json` is the source of truth for frontend transport types.
- Update backend schemas before changing generated frontend types.
- Keep manual frontend transport limited to auth bootstrap, SSE, uploads, and binary downloads.
- Do not add duplicated API mirror types when generated schemas already express the contract.

### Tests

Run the relevant checks before handing off backend changes:

```bash
uv run ruff check src tests scripts/run_eval_harness.py scripts/backfill_topics.py
uv run mypy src
uv run pytest tests -q
```

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```
