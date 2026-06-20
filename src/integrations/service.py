from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.api_keys.repository import ApiKeyRecord
from src.documents.schemas import ExternalIngestDTO, ExternalIngestResultDTO
from src.documents.types import DocumentType
from src.integrations.repository import (
    TelegramChatBindingRecord,
    TelegramPairingCodeRecord,
)
from src.integrations.schemas import (
    ApiKeyPrincipalDTO,
    ExternalConnectionDTO,
    NotionConnectionResponse,
    NotionPageResponse,
    TelegramChatBindingDTO,
    TelegramChatBindingResponse,
    TelegramPairingCodeResponse,
    TelegramStatusDTO,
    TelegramStatusResponse,
)
from src.kit.exceptions import InvalidTokenException, ResourceNotFoundException, ValidationException
from src.settings import settings

if TYPE_CHECKING:
    from src.api_keys.repository import ApiKeyRepository
    from src.documents.ingestion import ExternalItemIngester
    from src.integrations.clients import NotionOAuthClientProtocol, NotionWorkspaceClientProtocol
    from src.integrations.repository import ExternalConnectionRepository, TelegramRepository
    from src.kit.ports.security.token_cipher import ITokenCipher
    from src.kit.security.signed_state import SignedState
    from src.postgres import AsyncSession


ALLOWED_API_KEY_SCOPES = {"ingest:write", "status:read", "collections:read", "query:write"}
API_KEY_PREFIX = "con_"
LEGACY_API_KEY_PREFIXES = ("ctx_",)
TELEGRAM_PAIRING_TTL = timedelta(minutes=10)
TELEGRAM_API_KEY_SCOPES = ["ingest:write", "status:read"]


def notion_connection_dto(connection: ExternalConnectionDTO) -> NotionConnectionResponse:
    return NotionConnectionResponse(
        connected=True,
        workspace_id=connection.workspace_id,
        workspace_name=connection.workspace_name,
        bot_id=connection.bot_id,
        default_parent_page_id=connection.default_parent_page_id,
        default_parent_page_title=connection.default_parent_page_title,
    )


@dataclass(frozen=True, slots=True)
class ConsumeTelegramPairingCodeDTO:
    code: str
    chat_id: str
    chat_username: str | None = None
    chat_title: str | None = None


class ApiKeyAuthenticator:
    def __init__(self, session: AsyncSession, repository: ApiKeyRepository) -> None:
        self._session = session
        self._repository = repository

    async def __call__(self, token: str, *, required_scope: str) -> ApiKeyPrincipalDTO:
        if required_scope not in ALLOWED_API_KEY_SCOPES:
            raise ValidationException("unsupported api key scope")
        normalized = normalize_bearer_token(token)
        record = await self._repository.get_by_hash(hash_api_key(normalized))
        if record is None or record.revoked_at is not None or required_scope not in record.scopes:
            raise InvalidTokenException("invalid api key")
        await self._repository.mark_used(record.id, datetime.now(UTC))
        await self._session.flush()
        return ApiKeyPrincipalDTO(user_id=record.user_id, api_key_id=record.id, scopes=record.scopes)


class NotionConnectionService:
    def __init__(
        self,
        session: AsyncSession,
        repository: ExternalConnectionRepository,
        oauth_client: NotionOAuthClientProtocol,
        token_cipher: ITokenCipher,
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
        return notion_connection_dto(connection)

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
        return notion_connection_dto(connection)


class NotionWorkspaceService:
    def __init__(
        self,
        repository: ExternalConnectionRepository,
        workspace_client: NotionWorkspaceClientProtocol,
        token_cipher: ITokenCipher,
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
    ) -> ExternalIngestResultDTO:
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


class TelegramPairingService:
    def __init__(
        self,
        session: AsyncSession,
        api_key_repository: ApiKeyRepository,
        telegram_repository: TelegramRepository,
    ) -> None:
        self._session = session
        self._api_key_repository = api_key_repository
        self._telegram_repository = telegram_repository

    async def create_pairing_code(self, *, user_id: UUID) -> TelegramPairingCodeResponse:
        code = generate_pairing_code()
        token = generate_api_key_token()
        now = datetime.now(UTC)
        api_key = ApiKeyRecord(
            id=uuid4(),
            user_id=user_id,
            name="Telegram bot",
            key_hash=hash_api_key(token),
            prefix=token[:12],
            scopes=TELEGRAM_API_KEY_SCOPES,
            last_used_at=None,
            revoked_at=None,
            created_at=now,
        )
        pairing = TelegramPairingCodeRecord(
            id=uuid4(),
            user_id=user_id,
            api_key_id=api_key.id,
            code_hash=hash_pairing_code(code),
            expires_at=now + TELEGRAM_PAIRING_TTL,
            consumed_at=None,
            created_at=now,
        )
        await self._api_key_repository.create(api_key)
        created = await self._telegram_repository.create_pairing_code(pairing)
        await self._session.flush()
        return TelegramPairingCodeResponse(id=created.id, code=code, expires_at=created.expires_at)

    async def get_status(self, *, user_id: UUID) -> TelegramStatusDTO:
        bindings = await self._telegram_repository.list_bindings_by_user_id(user_id)
        return TelegramStatusDTO(bindings=[telegram_binding_dto(binding) for binding in bindings])

    async def revoke_binding(self, *, user_id: UUID, binding_id: UUID) -> None:
        now = datetime.now(UTC)
        binding = await self._telegram_repository.revoke_binding(
            user_id=user_id,
            binding_id=binding_id,
            revoked_at=now,
        )
        if binding is None:
            raise ResourceNotFoundException("telegram binding not found")
        if binding.api_key_id is not None:
            await self._api_key_repository.revoke(api_key_id=binding.api_key_id, user_id=user_id, revoked_at=now)
        await self._session.flush()

    async def consume_pairing_code(self, dto: ConsumeTelegramPairingCodeDTO) -> TelegramChatBindingDTO:
        now = datetime.now(UTC)
        pairing = await self._telegram_repository.get_pairing_code_by_hash(hash_pairing_code(dto.code))
        if pairing is None or pairing.consumed_at is not None or pairing.expires_at < now:
            raise ValidationException("invalid telegram pairing code")
        await self._telegram_repository.consume_pairing_code(pairing.id, now)
        binding = await self._telegram_repository.upsert_binding(
            user_id=pairing.user_id,
            api_key_id=pairing.api_key_id,
            chat_id=normalize_chat_id(dto.chat_id),
            chat_username=normalize_optional(dto.chat_username),
            chat_title=normalize_optional(dto.chat_title),
            paired_at=now,
        )
        await self._session.flush()
        return telegram_binding_dto(binding)


class TelegramIngestionService:
    def __init__(self, repository: TelegramRepository, ingest_external_item: ExternalItemIngester) -> None:
        self._repository = repository
        self._ingest_external_item = ingest_external_item

    async def ingest(self, *, chat_id: str, dto: ExternalIngestDTO) -> ExternalIngestResultDTO:
        binding = await self._repository.get_active_binding_by_chat_id(normalize_chat_id(chat_id))
        if binding is None:
            raise ResourceNotFoundException("telegram chat is not paired")
        return await self._ingest_external_item(
            replace(
                dto,
                user_id=binding.user_id,
                api_key_id=binding.api_key_id,
            )
        )




def generate_api_key_token() -> str:
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_bearer_token(value: str) -> str:
    token = value.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    valid_prefixes = (API_KEY_PREFIX, *LEGACY_API_KEY_PREFIXES)
    if not token.startswith(valid_prefixes):
        raise InvalidTokenException("invalid api key")
    return token


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


def telegram_binding_dto(record: TelegramChatBindingRecord) -> TelegramChatBindingDTO:
    return TelegramChatBindingDTO(
        id=record.id,
        user_id=record.user_id,
        api_key_id=record.api_key_id,
        chat_id=record.chat_id,
        chat_username=record.chat_username,
        chat_title=record.chat_title,
        paired_at=record.paired_at,
        revoked_at=record.revoked_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def generate_pairing_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


def hash_pairing_code(code: str) -> str:
    return hashlib.sha256(normalize_pairing_code(code).encode("utf-8")).hexdigest()


def normalize_pairing_code(code: str) -> str:
    normalized = code.strip().upper().replace(" ", "")
    if not normalized:
        raise ValidationException("telegram pairing code is required")
    return normalized


def normalize_chat_id(chat_id: str) -> str:
    normalized = str(chat_id).strip()
    if not normalized:
        raise ValidationException("telegram chat id is required")
    return normalized[:64]


def normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def to_notion_connection_response(dto: NotionConnectionResponse) -> NotionConnectionResponse:
    return NotionConnectionResponse(
        connected=dto.connected,
        workspace_id=dto.workspace_id,
        workspace_name=dto.workspace_name,
        bot_id=dto.bot_id,
        default_parent_page_id=dto.default_parent_page_id,
        default_parent_page_title=dto.default_parent_page_title,
    )


def to_notion_page_response(dto: NotionPageResponse) -> NotionPageResponse:
    return NotionPageResponse(id=dto.id, title=dto.title)


def to_telegram_pairing_code_response(dto: TelegramPairingCodeResponse) -> TelegramPairingCodeResponse:
    return TelegramPairingCodeResponse(id=dto.id, code=dto.code, expires_at=dto.expires_at)


def to_telegram_binding_response(dto: TelegramChatBindingDTO) -> TelegramChatBindingResponse:
    return TelegramChatBindingResponse(
        id=dto.id,
        chat_id=dto.chat_id,
        chat_username=dto.chat_username,
        chat_title=dto.chat_title,
        paired_at=dto.paired_at,
        revoked_at=dto.revoked_at,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_telegram_status_response(dto: TelegramStatusDTO) -> TelegramStatusResponse:
    return TelegramStatusResponse(bindings=[to_telegram_binding_response(binding) for binding in dto.bindings])
