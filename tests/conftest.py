import os

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")


@pytest.fixture(autouse=True)
def default_billing_entitlements(monkeypatch: pytest.MonkeyPatch) -> None:
    async def allow_document_creation(session: object, *, user_id: object) -> None:
        return None

    async def allow_api_key_creation(session: object, *, user_id: object) -> None:
        return None

    async def unlimited_workspace_members(session: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr("src.documents.service.billing.ensure_can_create_document", allow_document_creation)
    monkeypatch.setattr("src.documents.ingestion.billing.ensure_can_create_document", allow_document_creation)
    monkeypatch.setattr("src.documents.notes.billing.ensure_can_create_document", allow_document_creation)
    monkeypatch.setattr("src.repo_syncs.runner.billing.ensure_can_create_document", allow_document_creation)
    monkeypatch.setattr("src.api_keys.service.billing.ensure_can_create_api_key", allow_api_key_creation)
    monkeypatch.setattr("src.workspaces.service.billing.workspace_member_limit", unlimited_workspace_members)
    monkeypatch.setattr("src.collections.service.billing.member_limit_for_user", unlimited_workspace_members)
