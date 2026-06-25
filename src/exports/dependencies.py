from fastapi import Depends

from src.documents.exports import NotionMarkdownExporter
from src.integrations.notion_export_client import NotionExportClient
from src.integrations.repository import ExternalConnectionRepository
from src.kit.security.fernet_token_cipher import FernetTokenCipher
from src.postgres import AsyncSession, get_db_session
from src.settings import settings


def get_notion_export_client() -> NotionExportClient:
    return NotionExportClient()


def get_token_cipher() -> FernetTokenCipher:
    return FernetTokenCipher(settings.TOKEN_ENCRYPTION_KEY, key_version=settings.TOKEN_ENCRYPTION_KEY_VERSION)


def get_notion_markdown_exporter(
    session: AsyncSession = Depends(get_db_session),
    notion_export_client: NotionExportClient = Depends(get_notion_export_client),
    token_cipher: FernetTokenCipher = Depends(get_token_cipher),
) -> NotionMarkdownExporter:
    return NotionMarkdownExporter(ExternalConnectionRepository.from_session(session), notion_export_client, token_cipher)
