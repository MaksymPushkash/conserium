from __future__ import annotations

from datetime import datetime  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, Field, model_validator

from src.documents.schemas import DocumentResponse  # noqa: TC001
from src.documents.types import DocumentType


class ExternalIngestRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    type: DocumentType = DocumentType.TEXT
    collection_id: UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    source_url: str | None = None
    raw_content: str | None = Field(default=None, max_length=1_000_000)
    language: str | None = Field(default=None, max_length=10)
    external_id: str | None = Field(default=None, max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=200)
    provider: str | None = Field(default=None, max_length=80)
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_supported_external_source(self) -> ExternalIngestRequest:
        if self.type in (DocumentType.TEXT, DocumentType.MARKDOWN) and not (
            self.raw_content and self.raw_content.strip()
        ):
            raise ValueError("raw_content is required for text ingestion")
        if self.type in (DocumentType.URL, DocumentType.YOUTUBE) and self.source_url is None:
            raise ValueError(f"source_url is required for {self.type.value.lower()} ingestion")
        if self.type not in (DocumentType.TEXT, DocumentType.MARKDOWN, DocumentType.URL, DocumentType.YOUTUBE):
            raise ValueError("external ingest supports text, markdown, url, and youtube only")
        return self


class ExternalIntakeItemResponse(BaseModel):
    id: UUID
    provider: str
    external_id: str | None
    idempotency_key: str | None
    title: str
    type: DocumentType
    collection_id: UUID | None
    tags: list[str]
    source_url: str | None
    status: str
    error_reason: str | None
    document_id: UUID | None
    payload_metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime | None


class ExternalIngestResponse(BaseModel):
    intake_item: ExternalIntakeItemResponse
    document: DocumentResponse | None


class ExternalIntakeListResponse(BaseModel):
    items: list[ExternalIntakeItemResponse]
    limit: int
    offset: int
