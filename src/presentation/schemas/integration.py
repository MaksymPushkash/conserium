from pydantic import BaseModel


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
