from fastapi import Depends

from src.documents.exports import NotionMarkdownExporter
from src.integrations.clients import NotionExportClientProtocol
from src.integrations.notion_export_client import NotionExportClient
from src.integrations.repository import ExternalConnectionRepository
from src.kit.ports.security.token_cipher import ITokenCipher
from src.kit.security.fernet_token_cipher import FernetTokenCipher
from src.postgres import AsyncSession, get_db_session
from src.settings import settings


def get_notion_export_client() -> NotionExportClientProtocol:
    return NotionExportClient()


def get_token_cipher() -> ITokenCipher:
    return FernetTokenCipher(settings.TOKEN_ENCRYPTION_KEY, key_version=settings.TOKEN_ENCRYPTION_KEY_VERSION)


def get_notion_markdown_exporter(
    session: AsyncSession = Depends(get_db_session),
    notion_export_client: NotionExportClientProtocol = Depends(get_notion_export_client),
    token_cipher: ITokenCipher = Depends(get_token_cipher),
) -> NotionMarkdownExporter:
    return NotionMarkdownExporter(ExternalConnectionRepository.from_session(session), notion_export_client, token_cipher)
