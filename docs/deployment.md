# Deployment

The backend and frontend remain separate repositories and deploy independently:

- FastAPI and Celery run on the VPS.
- Next.js runs on Vercel.
- `openapi.json` is the compatibility contract between releases.

## Backend release order

1. Build candidate images without replacing running containers.
2. Start or verify PostgreSQL and Redis.
3. Run `alembic upgrade head` from a one-shot candidate app container.
4. Start the candidate app, workers, and scheduler.
5. Validate local health, public health, and retrieval behavior.

Migrations must use expand-contract changes. A candidate schema must remain compatible with the
previous backend and frontend because automatic rollback restores code but does not downgrade the
database.

## Frontend release order

Frontend production builds compare the generated client with the production backend OpenAPI
schema. A frontend build that depends on an undeployed backend contract fails before Vercel can
promote it. Deploy the backend first, verify production health, then rebuild the frontend.

Disable direct Vercel production promotion from Git pushes. Configure a production deploy hook as
the backend repository secret `VERCEL_DEPLOY_HOOK_URL`; the VPS workflow calls it only after backend
health and live retrieval validation succeed.

Repository topology does not determine deployment topology. A monorepo is unnecessary while the
product has one backend and one frontend with no shared TypeScript packages or additional clients.
