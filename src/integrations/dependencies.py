from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

from src.api_keys.repository import ApiKeyRepository
from src.documents.ingestion import get_external_item_ingester
from src.integrations.notion_oauth_client import NotionOAuthClient
from src.integrations.notion_workspace_client import NotionWorkspaceClient
from src.integrations.repository import (
    ExternalConnectionRepository,
    TelegramRepository,
)
from src.integrations.service import (
    ApiKeyAuthenticator,
    NotionConnectionService,
    NotionWorkspaceService,
    TelegramIngestionService,
    TelegramPairingService,
)
from src.kit.security.fernet_token_cipher import FernetTokenCipher
from src.kit.security.signed_state import SignedState
from src.postgres import AsyncSession, get_db_session
from src.settings import settings

if TYPE_CHECKING:
    from src.documents.ingestion import ExternalItemIngester
    from src.integrations.clients import NotionOAuthClientProtocol, NotionWorkspaceClientProtocol
    from src.kit.ports.security.token_cipher import ITokenCipher


def get_api_key_repository(session: AsyncSession = Depends(get_db_session)) -> ApiKeyRepository:
    return ApiKeyRepository.from_session(session)


def get_external_connection_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ExternalConnectionRepository:
    return ExternalConnectionRepository.from_session(session)


def get_telegram_repository(session: AsyncSession = Depends(get_db_session)) -> TelegramRepository:
    return TelegramRepository.from_session(session)


def get_api_key_authenticator(
    session: AsyncSession = Depends(get_db_session),
    repository: ApiKeyRepository = Depends(get_api_key_repository),
) -> ApiKeyAuthenticator:
    return ApiKeyAuthenticator(session, repository)


def get_token_cipher() -> ITokenCipher:
    return FernetTokenCipher(settings.TOKEN_ENCRYPTION_KEY, key_version=settings.TOKEN_ENCRYPTION_KEY_VERSION)


def get_notion_oauth_client() -> NotionOAuthClientProtocol:
    return NotionOAuthClient()


def get_notion_workspace_client() -> NotionWorkspaceClientProtocol:
    return NotionWorkspaceClient()


def _get_signed_state() -> SignedState:
    return SignedState(settings.JWT_SECRET)


def get_notion_connection_service(
    session: AsyncSession = Depends(get_db_session),
    repository: ExternalConnectionRepository = Depends(get_external_connection_repository),
    notion_oauth_client: NotionOAuthClientProtocol = Depends(get_notion_oauth_client),
    token_cipher: ITokenCipher = Depends(get_token_cipher),
) -> NotionConnectionService:
    return NotionConnectionService(session, repository, notion_oauth_client, token_cipher, _get_signed_state())


def get_notion_workspace_service(
    repository: ExternalConnectionRepository = Depends(get_external_connection_repository),
    notion_workspace_client: NotionWorkspaceClientProtocol = Depends(get_notion_workspace_client),
    token_cipher: ITokenCipher = Depends(get_token_cipher),
    ingest_external_item: ExternalItemIngester = Depends(get_external_item_ingester),
) -> NotionWorkspaceService:
    return NotionWorkspaceService(repository, notion_workspace_client, token_cipher, ingest_external_item)


def get_telegram_pairing_service(
    session: AsyncSession = Depends(get_db_session),
    api_key_repository: ApiKeyRepository = Depends(get_api_key_repository),
    telegram_repository: TelegramRepository = Depends(get_telegram_repository),
) -> TelegramPairingService:
    return TelegramPairingService(session, api_key_repository, telegram_repository)


def get_telegram_ingestion_service(
    repository: TelegramRepository = Depends(get_telegram_repository),
    ingest_external_item: ExternalItemIngester = Depends(get_external_item_ingester),
) -> TelegramIngestionService:
    return TelegramIngestionService(repository, ingest_external_item)


__all__ = [
    "get_api_key_authenticator",
    "get_notion_connection_service",
    "get_notion_oauth_client",
    "get_notion_workspace_client",
    "get_notion_workspace_service",
    "get_telegram_ingestion_service",
    "get_telegram_pairing_service",
    "get_token_cipher",
]
