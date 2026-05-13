from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class CollectionResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    color: str | None
    created_at: datetime
    updated_at: datetime | None


class CollectionListResponse(BaseModel):
    items: list[CollectionResponse]
    total: int
    limit: int
    offset: int
