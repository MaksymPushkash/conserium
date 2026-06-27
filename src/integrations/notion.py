from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.documents.types import DocumentType
from src.integrations.schemas import (
    ExternalConnectionRecord,
    NotionConnectionResponse,
    NotionPageResponse,
)
from src.kit.exceptions import InvalidTokenException, ResourceNotFoundException, ValidationException
from src.settings import settings

if TYPE_CHECKING:
    from src.documents.ingestion import ExternalItemIngester
    from src.documents.schemas import ExternalIngestResult
    from src.integrations.notion_oauth_client import NotionOAuthClient
    from src.integrations.notion_workspace_client import NotionWorkspaceClient
    from src.integrations.repository import ExternalConnectionRepository
    from src.kit.security.fernet_token_cipher import FernetTokenCipher
    from src.kit.security.signed_state import SignedState
    from src.postgres import AsyncSession


def notion_connection_response(connection: ExternalConnectionRecord) -> NotionConnectionResponse:
    return NotionConnectionResponse(
        connected=True,
        workspace_id=connection.workspace_id,
        workspace_name=connection.workspace_name,
        bot_id=connection.bot_id,
        default_parent_page_id=connection.default_parent_page_id,
        default_parent_page_title=connection.default_parent_page_title,
    )


class NotionConnectionService:
    def __init__(
        self,
        session: AsyncSession,
        repository: ExternalConnectionRepository,
        oauth_client: NotionOAuthClient,
        token_cipher: FernetTokenCipher,
        signed_state: SignedState,
    ) -> None:
        self._session = session
        self._repository = repository
        self._oauth_client = oauth_client
        self._token_cipher = token_cipher
        self._signed_state = signed_state

    async def get(self, *, user_id: UUID) -> NotionConnectionResponse:
        connection = await self._repository.get_by_provider(user_id=user_id, provider="notion")
        if connection is None:
            return NotionConnectionResponse(
                connected=False,
                workspace_id=None,
                workspace_name=None,
                bot_id=None,
                default_parent_page_id=None,
                default_parent_page_title=None,
            )
        return notion_connection_response(connection)

    async def create_connect_url(self, *, user_id: UUID, redirect_uri: str) -> str:
        state = self._signed_state.sign({"user_id": str(user_id), "provider": "notion"})
        return self._oauth_client.authorization_url(redirect_uri=redirect_uri, state=state)

    async def complete(self, *, code: str, state: str, redirect_uri: str) -> None:
        payload = self._signed_state.verify(state)
        if payload.get("provider") != "notion" or not isinstance(payload.get("user_id"), str):
            raise InvalidTokenException("invalid state")
        user_id = UUID(payload["user_id"])
        token = await self._oauth_client.exchange_code(code=code, redirect_uri=redirect_uri)
        await self._repository.upsert(
            user_id=user_id,
            provider="notion",
            workspace_id=token.workspace_id,
            workspace_name=token.workspace_name,
            access_token_encrypted=self._token_cipher.encrypt(token.access_token),
            bot_id=token.bot_id,
            owner=token.owner,
        )
        await self._session.flush()

    async def disconnect(self, *, user_id: UUID) -> None:
        await self._repository.delete_by_provider(user_id=user_id, provider="notion")
        await self._session.flush()

    async def update_settings(
        self,
        *,
        user_id: UUID,
        default_parent_page_id: str | None,
        default_parent_page_title: str | None,
    ) -> NotionConnectionResponse:
        parent_page_id = normalize_notion_parent_page_id(default_parent_page_id)
        parent_page_title = normalize_notion_parent_page_title(default_parent_page_title) if parent_page_id else None
        connection = await self._repository.update_settings(
            user_id=user_id,
            provider="notion",
            default_parent_page_id=parent_page_id,
            default_parent_page_title=parent_page_title,
        )
        if connection is None:
            raise ResourceNotFoundException("notion connection not found")
        await self._session.flush()
        return notion_connection_response(connection)


class NotionWorkspaceService:
    def __init__(
        self,
        repository: ExternalConnectionRepository,
        workspace_client: NotionWorkspaceClient,
        token_cipher: FernetTokenCipher,
        ingest_external_item: ExternalItemIngester,
    ) -> None:
        self._repository = repository
        self._workspace_client = workspace_client
        self._token_cipher = token_cipher
        self._ingest_external_item = ingest_external_item

    async def search_pages(self, *, user_id: UUID, query: str | None, limit: int) -> list[NotionPageResponse]:
        connection = await self._repository.get_by_provider(user_id=user_id, provider="notion")
        if connection is None:
            raise ResourceNotFoundException("notion connection not found")
        try:
            access_token = self._token_cipher.decrypt(connection.access_token_encrypted)
        except ValueError as exc:
            raise ValidationException("reconnect Notion before searching pages") from exc
        return await self._workspace_client.search_pages(
            access_token=access_token,
            query=normalize_optional_text(query),
            limit=max(1, min(limit, 25)),
        )

    async def import_page(
        self,
        *,
        user_id: UUID,
        page_id: str,
        collection_id: UUID | None,
        tags: list[str],
    ) -> ExternalIngestResult:
        notion_page_id = normalize_notion_parent_page_id(page_id)
        if notion_page_id is None:
            raise ValidationException("notion page id is required")
        connection = await self._repository.get_by_provider(user_id=user_id, provider="notion")
        if connection is None:
            raise ResourceNotFoundException("notion connection not found")
        try:
            access_token = self._token_cipher.decrypt(connection.access_token_encrypted)
        except ValueError as exc:
            raise ValidationException("reconnect Notion before importing pages") from exc
        page = await self._workspace_client.get_page_markdown(access_token=access_token, page_id=notion_page_id)
        return await self._ingest_external_item(
            user_id=user_id,
            api_key_id=None,
            provider="notion",
            external_id=page.id,
            idempotency_key=f"notion:{page.id}",
            title=page.title,
            type=DocumentType.MARKDOWN,
            collection_id=collection_id,
            tags=tags,
            raw_content=page.markdown,
            payload_metadata={"notion_page_id": page.id, "notion_workspace_id": connection.workspace_id or ""},
        )


def normalize_notion_parent_page_id(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if len(normalized) > 120:
        raise ValidationException("notion parent page id is too long")
    return normalized


def normalize_notion_parent_page_title(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if len(normalized) > 300:
        raise ValidationException("notion parent page title is too long")
    return normalized


def normalize_optional_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def notion_settings_redirect(status: str) -> str:
    return f"{settings.FRONTEND_URL}/settings?integration=notion&status={status}"


__all__ = [
    "NotionConnectionService",
    "NotionWorkspaceService",
    "normalize_notion_parent_page_id",
    "normalize_notion_parent_page_title",
    "normalize_optional_text",
    "notion_connection_response",
    "notion_settings_redirect",
]
