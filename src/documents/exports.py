from __future__ import annotations

from textwrap import wrap
from typing import TYPE_CHECKING

from fastapi import Depends

from src.documents.activity_repository import DocumentActivityRepository
from src.documents.document_repository import DocumentRepository
from src.documents.schemas import ExportedFileDTO, GetDocumentDTO, NotionExportDTO, NotionExportResultDTO
from src.documents.service import ensure_document_owner
from src.kit.exceptions import DocumentNotFoundException, IntegrationConfigurationException, ValidationException
from src.postgres import AsyncSession, get_db_session

if TYPE_CHECKING:
    from src.integrations.clients import NotionExportClientProtocol
    from src.integrations.repository import ExternalConnectionRepository
    from src.kit.ports.security.token_cipher import ITokenCipher
    from src.models.document import DocumentModel


def get_document_exporter(
    session: AsyncSession = Depends(get_db_session),
) -> DocumentExporter:
    return DocumentExporter(
        session,
        DocumentRepository.from_session(session),
        DocumentActivityRepository.from_session(session),
    )


class DocumentExporter:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        document_activity_repo: DocumentActivityRepository,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._document_activity_repo = document_activity_repo

    async def __call__(self, dto: GetDocumentDTO, *, export_format: str) -> ExportedFileDTO:
        document = await self._load_document(dto)
        markdown = document_to_markdown(document)
        normalized_format = export_format.lower()
        filename_stem = safe_filename(document.title)
        if normalized_format in {"md", "markdown"}:
            return ExportedFileDTO(
                filename=f"{filename_stem}.md",
                media_type="text/markdown; charset=utf-8",
                content=markdown.encode("utf-8"),
            )
        if normalized_format == "pdf":
            return ExportedFileDTO(
                filename=f"{filename_stem}.pdf",
                media_type="application/pdf",
                content=markdown_to_pdf(markdown),
            )
        raise ValidationException("unsupported export format")

    async def _load_document(self, dto: GetDocumentDTO) -> DocumentModel:
        document = await self._document_repo.get_by_id(dto.document_id)
        if document is None:
            raise DocumentNotFoundException("document not found")
        ensure_document_owner(document, dto.user_id)
        await self._document_activity_repo.record_event(
            user_id=dto.user_id,
            document_id=document.id,
            event_type="exported",
        )
        await self._session.flush()
        return document


def document_to_markdown(document: DocumentModel) -> str:
    parts = [f"# {document.title}", ""]
    metadata = [
        f"- Type: {document.type.value}",
        f"- Status: {document.status.value}",
        f"- Created: {document.created_at.isoformat()}",
    ]
    if document.source_url:
        metadata.append(f"- Source: {document.source_url}")
    if document.language:
        metadata.append(f"- Language: {document.language}")
    if document.tags:
        metadata.append(f"- Tags: {', '.join(document.tags)}")
    parts.extend(metadata)
    if document.summary:
        parts.extend(["", "## Summary", "", document.summary])
    if document.raw_content:
        parts.extend(["", "## Content", "", document.raw_content])
    return "\n".join(parts).strip() + "\n"


def safe_filename(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in ("-", "_", " ") else "-" for char in value)
    normalized = "-".join(cleaned.strip().split())
    return normalized[:80] or "document"


def markdown_to_pdf(markdown: str) -> bytes:
    lines = _pdf_lines(markdown)
    page_streams = [_page_stream(page_lines) for page_lines in _pages(lines)]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        _pages_object(len(page_streams)),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    page_object_numbers: list[int] = []
    for index, stream in enumerate(page_streams):
        page_object_number = 4 + index * 2
        content_object_number = page_object_number + 1
        page_object_numbers.append(page_object_number)
        objects.append(_page_object(content_object_number))
        objects.append(_stream_object(stream))
    objects[1] = _pages_object(len(page_streams), page_object_numbers)
    return _pdf_document(objects)


def _pdf_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    for raw_line in markdown.splitlines():
        if not raw_line.strip():
            lines.append("")
            continue
        lines.extend(wrap(raw_line, width=92, replace_whitespace=False) or [""])
    return lines


def _pages(lines: list[str]) -> list[list[str]]:
    page_size = 46
    pages = [lines[index : index + page_size] for index in range(0, len(lines), page_size)]
    return pages or [[""]]


def _page_stream(lines: list[str]) -> bytes:
    content = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
    for line in lines:
        content.append(f"({_escape_pdf_text(line)}) Tj")
        content.append("T*")
    content.append("ET")
    return "\n".join(content).encode("utf-8")


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pages_object(page_count: int, page_object_numbers: list[int] | None = None) -> bytes:
    kids = page_object_numbers or [4 + index * 2 for index in range(page_count)]
    kids_ref = " ".join(f"{number} 0 R" for number in kids)
    return f"<< /Type /Pages /Kids [{kids_ref}] /Count {page_count} >>".encode()


def _page_object(content_object_number: int) -> bytes:
    return (
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
        f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_object_number} 0 R >>"
    ).encode()


def _stream_object(stream: bytes) -> bytes:
    return b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"


def _pdf_document(objects: list[bytes]) -> bytes:
    body = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body.extend(f"{index} 0 obj\n".encode())
        body.extend(obj)
        body.extend(b"\nendobj\n")
    xref_offset = len(body)
    body.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode())
    body.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(body)


class NotionMarkdownExporter:
    def __init__(
        self,
        external_connection_repo: ExternalConnectionRepository,
        notion_client: NotionExportClientProtocol,
        token_cipher: ITokenCipher,
    ) -> None:
        self._external_connection_repo = external_connection_repo
        self._notion_client = notion_client
        self._token_cipher = token_cipher

    async def __call__(self, dto: NotionExportDTO) -> NotionExportResultDTO:
        access_token = None
        connection = await self._external_connection_repo.get_by_provider(user_id=dto.user_id, provider="notion")
        parent_page_id = dto.parent_page_id
        if connection is not None:
            try:
                access_token = self._token_cipher.decrypt(connection.access_token_encrypted)
            except ValueError as exc:
                raise IntegrationConfigurationException("reconnect Notion before exporting") from exc
            parent_page_id = parent_page_id or connection.default_parent_page_id
            if not parent_page_id:
                raise IntegrationConfigurationException("set a default Notion parent page before exporting")

        page_id, url = await self._notion_client.create_markdown_page(
            title=dto.title,
            markdown=dto.markdown,
            parent_page_id=parent_page_id,
            access_token=access_token,
        )
        return NotionExportResultDTO(page_id=page_id, url=url)
