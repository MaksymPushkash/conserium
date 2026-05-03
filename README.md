# Cortex

Cortex is a personal AI knowledge backend. It ingests saved content, processes it asynchronously, stores chunks and embeddings, and answers natural-language questions with sources, citations, REFRAG context packaging, and streaming output.

Current backend docs:

- [Public API](docs/public-api.md)
- [Local Development](docs/local-development.md)
- [Project Status and Roadmap](docs/project-status-and-roadmap.md)

Quick local start:

```bash
docker compose up -d postgres redis rabbitmq
uv sync
uv run alembic upgrade head
docker compose up --build
```

API docs are available at `http://localhost:8000/docs`.
