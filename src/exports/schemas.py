from pydantic import BaseModel, Field


class MarkdownExportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(min_length=1, max_length=1_000_000)
    format: str = Field(pattern="^(markdown|md|pdf)$")


class NotionExportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(min_length=1, max_length=1_000_000)
    parent_page_id: str | None = Field(default=None, max_length=120)


class NotionExportResponse(BaseModel):
    page_id: str
    url: str | None
