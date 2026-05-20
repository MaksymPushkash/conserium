from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType


class CollectionShareResponse(BaseModel):
    id: UUID
    collection_id: UUID
    slug: str
    include_summaries: bool
    include_notes: bool
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class PublicCollectionDocumentResponse(BaseModel):
    id: UUID
    title: str
    type: DocumentType
    status: DocumentStatus
    source_url: str | None
    summary: str | None
    word_count: int | None
    language: str | None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None


class PublicCollectionResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    color: str | None
    documents: list[PublicCollectionDocumentResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None
