

## General Guidelines

- Do not add comments to the code unless necessary. The code should be self-explanatory.
- Use meaningful variable and function names.
- Follow good practices and code conventions.
- Make sure that all the new code is maintanable and follows the SOLID principles.
- Do not modify unrelated code to the task or issue you are working on.

## Architecture

Conserium is a feature-first modular monolith.

- Keep feature behavior under `src/{feature}`.
- Keep FastAPI handlers in `endpoints.py` thin.
- Keep business orchestration in feature service modules.
- Keep SQLAlchemy statements and persistence operations in repository modules.
- Keep shared SQLAlchemy models in `src/models`.
- Keep cross-cutting helpers and external adapter protocols in `src/kit`.
- Keep Celery configuration in `src/worker` and task entry points in feature `tasks.py` files.
- Use FastAPI dependencies. Do not introduce a dependency injection container.
- Do not recreate `application`, `presentation`, `domain`, `infrastructure`, `use_cases`, `dtos`, or feature-local `ports` layers.
- Do not create empty convention files. Add `auth.py`, `sorting.py`, or `tasks.py` only when the feature owns that behavior.
- Let the request or worker boundary own transactions. Request-path services must not call `session.commit()`.

See `docs/architecture.md` for the complete structure and enforced boundaries.

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
