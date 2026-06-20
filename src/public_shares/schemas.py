from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.documents.status import DocumentStatus
from src.documents.types import DocumentType


@dataclass(frozen=True, slots=True)
class AnswerShareSourceDTO:
    chunk_id: UUID
    document_id: UUID
    document_title: str | None
    content: str
    page_number: int | None
    chunk_index: int
    citation: str
    used_in_answer: bool


@dataclass(frozen=True, slots=True)
class AnswerShareDTO:
    id: UUID
    slug: str
    user_id: UUID
    collection_id: UUID | None
    collection_name: str | None
    conversation_id: UUID | None
    public_collection_slug: str | None
    query_text: str
    answer_text: str
    sources: list[AnswerShareSourceDTO]
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class CollectionShareDTO:
    id: UUID
    collection_id: UUID
    user_id: UUID
    slug: str
    include_summaries: bool
    include_notes: bool
    ask_enabled: bool
    daily_ask_limit: int
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class PublicAskEventDTO:
    id: UUID
    share_slug: str
    status: str
    reason: str | None
    query_text: str
    answer_share_slug: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PublicCollectionDocumentDTO:
    id: UUID
    title: str
    type: DocumentType
    status: DocumentStatus
    source_url: str | None
    summary: str | None
    word_count: int | None
    language: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class PublicCollectionDTO:
    id: UUID
    name: str
    description: str | None
    color: str | None
    documents: list[PublicCollectionDocumentDTO]
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


class AnswerShareSourceResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str | None
    content: str
    page_number: int | None
    chunk_index: int
    citation: str
    used_in_answer: bool


class AnswerShareResponse(BaseModel):
    slug: str
    url_path: str
    query: str
    answer: str
    sources: list[AnswerShareSourceResponse]
    collection_id: UUID | None
    collection_name: str | None
    public_collection_slug: str | None
    created_at: datetime
    revoked_at: datetime | None


class AnswerShareListResponse(BaseModel):
    items: list[AnswerShareResponse]


class PublicAnswerShareSourceResponse(BaseModel):
    document_title: str | None
    content: str
    page_number: int | None
    chunk_index: int
    citation: str
    used_in_answer: bool


class PublicAnswerShareResponse(BaseModel):
    slug: str
    url_path: str
    query: str
    answer: str
    sources: list[PublicAnswerShareSourceResponse]
    public_collection_slug: str | None
    created_at: datetime
