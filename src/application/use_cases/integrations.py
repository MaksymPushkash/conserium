from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.application.dtos.external_connection_dtos import NotionConnectionDTO, NotionPageDTO
from src.application.dtos.external_intake_dtos import ExternalIngestDTO, ExternalIngestResultDTO
from src.core.config import settings
from src.domain.exceptions import InvalidTokenException, ResourceNotFoundException, ValidationException
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.integrations.notion_oauth_client import INotionOAuthClient
    from src.application.ports.integrations.notion_workspace_client import INotionWorkspaceClient
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.application.ports.security.token_cipher import ITokenCipher
    from src.application.use_cases.external_intake import IngestExternalItemUseCase
    from src.infrastructure.security.signed_state import SignedState


class GetNotionConnectionUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID) -> NotionConnectionDTO:
        async with self._uow:
            connection = await self._uow.external_connection_repo.get_by_provider(user_id=user_id, provider="notion")
        if connection is None:
            return NotionConnectionDTO(connected=False)
        return NotionConnectionDTO(
            connected=True,
            workspace_id=connection.workspace_id,
            workspace_name=connection.workspace_name,
            bot_id=connection.bot_id,
            default_parent_page_id=connection.default_parent_page_id,
            default_parent_page_title=connection.default_parent_page_title,
        )


class CreateNotionConnectUrlUseCase:
    def __init__(self, oauth_client: INotionOAuthClient, signed_state: SignedState) -> None:
        self._oauth_client = oauth_client
        self._signed_state = signed_state

    async def __call__(self, *, user_id: UUID, redirect_uri: str) -> str:
        state = self._signed_state.sign({"user_id": str(user_id), "provider": "notion"})
        return self._oauth_client.authorization_url(redirect_uri=redirect_uri, state=state)


class CompleteNotionConnectionUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        oauth_client: INotionOAuthClient,
        token_cipher: ITokenCipher,
        signed_state: SignedState,
    ) -> None:
        self._uow = uow
        self._oauth_client = oauth_client
        self._token_cipher = token_cipher
        self._signed_state = signed_state

    async def __call__(self, *, code: str, state: str, redirect_uri: str) -> None:
        payload = self._signed_state.verify(state)
        if payload.get("provider") != "notion" or not isinstance(payload.get("user_id"), str):
            raise InvalidTokenException("invalid state")
        user_id = UUID(payload["user_id"])
        token = await self._oauth_client.exchange_code(code=code, redirect_uri=redirect_uri)
        async with self._uow:
            await self._uow.external_connection_repo.upsert(
                user_id=user_id,
                provider="notion",
                workspace_id=token.workspace_id,
                workspace_name=token.workspace_name,
                access_token_encrypted=self._token_cipher.encrypt(token.access_token),
                bot_id=token.bot_id,
                owner=token.owner,
            )
            await self._uow.commit()


class DisconnectNotionUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID) -> None:
        async with self._uow:
            await self._uow.external_connection_repo.delete_by_provider(user_id=user_id, provider="notion")
            await self._uow.commit()


class UpdateNotionConnectionSettingsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(
        self,
        *,
        user_id: UUID,
        default_parent_page_id: str | None,
        default_parent_page_title: str | None,
    ) -> NotionConnectionDTO:
        parent_page_id = normalize_notion_parent_page_id(default_parent_page_id)
        parent_page_title = normalize_notion_parent_page_title(default_parent_page_title) if parent_page_id else None
        async with self._uow:
            connection = await self._uow.external_connection_repo.update_settings(
                user_id=user_id,
                provider="notion",
                default_parent_page_id=parent_page_id,
                default_parent_page_title=parent_page_title,
            )
            if connection is None:
                raise ResourceNotFoundException("notion connection not found")
            await self._uow.commit()
        return NotionConnectionDTO(
            connected=True,
            workspace_id=connection.workspace_id,
            workspace_name=connection.workspace_name,
            bot_id=connection.bot_id,
            default_parent_page_id=connection.default_parent_page_id,
            default_parent_page_title=connection.default_parent_page_title,
        )


class SearchNotionPagesUseCase:
    def __init__(self, uow: IUnitOfWork, workspace_client: INotionWorkspaceClient, token_cipher: ITokenCipher) -> None:
        self._uow = uow
        self._workspace_client = workspace_client
        self._token_cipher = token_cipher

    async def __call__(self, *, user_id: UUID, query: str | None, limit: int) -> list[NotionPageDTO]:
        async with self._uow:
            connection = await self._uow.external_connection_repo.get_by_provider(user_id=user_id, provider="notion")
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


class ImportNotionPageUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        workspace_client: INotionWorkspaceClient,
        token_cipher: ITokenCipher,
        ingest_external_item: IngestExternalItemUseCase,
    ) -> None:
        self._uow = uow
        self._workspace_client = workspace_client
        self._token_cipher = token_cipher
        self._ingest_external_item = ingest_external_item

    async def __call__(
        self,
        *,
        user_id: UUID,
        page_id: str,
        collection_id: UUID | None,
        tags: list[str],
    ) -> ExternalIngestResultDTO:
        notion_page_id = normalize_notion_parent_page_id(page_id)
        if notion_page_id is None:
            raise ValidationException("notion page id is required")
        async with self._uow:
            connection = await self._uow.external_connection_repo.get_by_provider(user_id=user_id, provider="notion")
        if connection is None:
            raise ResourceNotFoundException("notion connection not found")
        try:
            access_token = self._token_cipher.decrypt(connection.access_token_encrypted)
        except ValueError as exc:
            raise ValidationException("reconnect Notion before importing pages") from exc
        page = await self._workspace_client.get_page_markdown(access_token=access_token, page_id=notion_page_id)
        return await self._ingest_external_item(
            ExternalIngestDTO(
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
