from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExportedFileDTO:
    filename: str
    media_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class NotionExportDTO:
    user_id: UUID
    title: str
    markdown: str
    parent_page_id: str | None = None


@dataclass(frozen=True, slots=True)
class NotionExportResultDTO:
    page_id: str
    url: str | None
