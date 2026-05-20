import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.application.dtos.export_dtos import NotionExportDTO
from src.application.dtos.external_connection_dtos import ExternalConnectionDTO
from src.application.use_cases.documents.export_document_use_case import (
    document_to_markdown,
    markdown_to_pdf,
    safe_filename,
)
from src.application.use_cases.documents.export_markdown_to_notion_use_case import ExportMarkdownToNotionUseCase
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import IntegrationConfigurationException
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType
from src.infrastructure.integrations.notion_export_client import markdown_to_notion_blocks

if TYPE_CHECKING:
    from src.application.ports.integrations.notion_export_client import INotionExportClient
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.application.ports.security.token_cipher import ITokenCipher


class _FakeExternalConnectionRepository:
    def __init__(self, connection: ExternalConnectionDTO | None) -> None:
        self._connection = connection

    async def get_by_provider(self, *, user_id: uuid.UUID, provider: str) -> ExternalConnectionDTO | None:
        return self._connection


class _FakeUnitOfWork:
    def __init__(self, connection: ExternalConnectionDTO | None) -> None:
        self.external_connection_repo = _FakeExternalConnectionRepository(connection)

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _FakeTokenCipher:
    def decrypt(self, value: str) -> str:
        return f"decrypted:{value}"

    def encrypt(self, value: str) -> str:
        return value


class _FakeNotionClient:
    def __init__(self) -> None:
        self.access_token: str | None = None
        self.parent_page_id: str | None = None

    async def create_markdown_page(
        self,
        *,
        title: str,
        markdown: str,
        parent_page_id: str | None = None,
        access_token: str | None = None,
    ) -> tuple[str, str | None]:
        self.access_token = access_token
        self.parent_page_id = parent_page_id
        return "page-id", "https://notion.test/page-id"


def test_document_to_markdown_includes_summary_content_and_source() -> None:
    document = _make_document()

    markdown = document_to_markdown(document)

    assert markdown.startswith("# Async Python")
    assert "## Summary" in markdown
    assert "Short summary." in markdown
    assert "## Content" in markdown
    assert "asyncio gathers work." in markdown
    assert "https://example.com/async-python" in markdown


def test_markdown_to_pdf_returns_pdf_bytes() -> None:
    content = markdown_to_pdf("# Async Python\n\nShort summary.")

    assert content.startswith(b"%PDF-1.4")
    assert b"%%EOF" in content


def test_safe_filename_normalizes_document_title() -> None:
    assert safe_filename("Async Python: notes / draft") == "Async-Python--notes---draft"


def test_markdown_to_notion_blocks_converts_basic_markdown() -> None:
    blocks = markdown_to_notion_blocks("# Title\n\n## Section\n\n- Item\n\nParagraph")

    assert [block["type"] for block in blocks] == [
        "heading_1",
        "heading_2",
        "bulleted_list_item",
        "paragraph",
    ]


@pytest.mark.asyncio
async def test_notion_export_uses_connected_user_token() -> None:
    user_id = uuid.uuid4()
    connection = ExternalConnectionDTO(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="notion",
        workspace_id="workspace-id",
        workspace_name="Workspace",
        access_token_encrypted="encrypted-token",
        bot_id=None,
        owner=None,
        default_parent_page_id="parent-page-id",
        default_parent_page_title="Parent page",
    )
    client = _FakeNotionClient()
    use_case = ExportMarkdownToNotionUseCase(
        cast("IUnitOfWork", _FakeUnitOfWork(connection)),
        cast("INotionExportClient", client),
        cast("ITokenCipher", _FakeTokenCipher()),
    )

    result = await use_case(NotionExportDTO(user_id=user_id, title="Draft", markdown="# Draft"))

    assert result.page_id == "page-id"
    assert client.access_token == "decrypted:encrypted-token"
    assert client.parent_page_id == "parent-page-id"


@pytest.mark.asyncio
async def test_notion_export_requires_parent_page_for_connected_user() -> None:
    user_id = uuid.uuid4()
    connection = ExternalConnectionDTO(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="notion",
        workspace_id="workspace-id",
        workspace_name="Workspace",
        access_token_encrypted="encrypted-token",
        bot_id=None,
        owner=None,
        default_parent_page_id=None,
        default_parent_page_title=None,
    )
    use_case = ExportMarkdownToNotionUseCase(
        cast("IUnitOfWork", _FakeUnitOfWork(connection)),
        cast("INotionExportClient", _FakeNotionClient()),
        cast("ITokenCipher", _FakeTokenCipher()),
    )

    with pytest.raises(IntegrationConfigurationException, match="default Notion parent page"):
        await use_case(NotionExportDTO(user_id=user_id, title="Draft", markdown="# Draft"))


def _make_document() -> DocumentEntity:
    return DocumentEntity(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        collection_id=None,
        title="Async Python",
        type=DocumentType.MARKDOWN,
        status=DocumentStatus.READY,
        source_url="https://example.com/async-python",
        file_path=None,
        file_size_bytes=None,
        raw_content="asyncio gathers work.",
        summary="Short summary.",
        word_count=3,
        language="en",
        entities=None,
        categories=None,
        visual_metadata=None,
        suggested_questions=[],
        tags=["python", "async"],
        doc_embedding=None,
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=datetime.now(UTC),
        updated_at=None,
    )
