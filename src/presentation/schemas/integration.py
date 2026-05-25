from uuid import UUID

from pydantic import BaseModel, Field

from src.presentation.schemas.external_intake import ExternalIngestResponse


class NotionConnectionResponse(BaseModel):
    connected: bool
    workspace_id: str | None
    workspace_name: str | None
    bot_id: str | None
    default_parent_page_id: str | None
    default_parent_page_title: str | None


class IntegrationConnectUrlResponse(BaseModel):
    url: str


class NotionConnectionSettingsRequest(BaseModel):
    default_parent_page_id: str | None = None
    default_parent_page_title: str | None = None


class NotionPageResponse(BaseModel):
    id: str
    title: str


class NotionImportRequest(BaseModel):
    page_id: str = Field(min_length=1, max_length=120)
    collection_id: UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)


class NotionImportResponse(ExternalIngestResponse): ...
