from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.documents.types import DocumentType
from src.query.schemas import QuerySource


@dataclass(frozen=True, slots=True)
class DraftTemplate:
    id: str
    name: str
    description: str
    prompt: str
    outline: list[str]


@dataclass(frozen=True, slots=True)
class DraftGenerationPayload:
    user_id: UUID
    prompt: str
    draft_id: UUID | None = None
    template_id: str = "brief"
    scope_type: str = "all"
    collection_id: UUID | None = None
    document_ids: tuple[UUID, ...] | None = None
    topic: str | None = None
    knowledge_gap_id: str | None = None
    outline: tuple[str, ...] | None = None
    tag_names: tuple[str, ...] | None = None
    document_types: tuple[DocumentType, ...] | None = None
    limit: int = 8


@dataclass(frozen=True, slots=True)
class DraftResult:
    draft_id: UUID
    version_id: UUID
    version_number: int
    prompt: str
    template_id: str
    scope_type: str
    markdown: str
    sources: list[QuerySource]
    gaps: list[str]


@dataclass(frozen=True, slots=True)
class DraftOutline:
    prompt: str
    template_id: str
    scope_type: str
    title: str
    sections: list[str]


@dataclass(frozen=True, slots=True)
class DraftListItem:
    id: UUID
    collection_id: UUID | None
    title: str
    prompt: str
    template_id: str
    scope_type: str
    topic: str | None
    knowledge_gap_id: str | None
    version_number: int
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class DraftListResult:
    items: list[DraftListItem]
    total: int


@dataclass(frozen=True, slots=True)
class DraftDetail:
    id: UUID
    collection_id: UUID | None
    current_version_id: UUID
    title: str
    prompt: str
    template_id: str
    scope_type: str
    topic: str | None
    knowledge_gap_id: str | None
    scope_metadata: dict[str, object]
    markdown: str
    sources: list[QuerySource]
    gaps: list[str]
    version_number: int
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class DraftVersion:
    id: UUID
    draft_id: UUID
    version_number: int
    title: str
    prompt: str
    template_id: str
    scope_type: str
    collection_id: UUID | None
    topic: str | None
    knowledge_gap_id: str | None
    markdown: str
    sources: list[QuerySource]
    gaps: list[str]
    created_at: datetime


class QuerySourceResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str | None
    content: str
    page_number: int | None
    chunk_index: int
    score: float | None
    citation: str
    used_in_answer: bool = False


class DraftGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    draft_id: UUID | None = None
    template_id: str = Field(default="brief", min_length=1, max_length=80)
    scope_type: str = Field(default="all", min_length=1, max_length=32)
    collection_id: UUID | None = None
    document_ids: list[UUID] | None = Field(default=None, max_length=50)
    topic: str | None = Field(default=None, max_length=100)
    knowledge_gap_id: str | None = Field(default=None, max_length=160)
    outline: list[str] | None = Field(default=None, max_length=30)
    tag_names: list[str] | None = Field(default=None, max_length=20)
    document_types: list[DocumentType] | None = None
    limit: int = Field(default=8, ge=1, le=20)


class DraftTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    prompt: str
    outline: list[str]


class DraftTemplateListResponse(BaseModel):
    items: list[DraftTemplateResponse]


class DraftOutlineResponse(BaseModel):
    prompt: str
    template_id: str
    scope_type: str
    title: str
    sections: list[str]


class DraftResponse(BaseModel):
    draft_id: UUID
    version_id: UUID
    version_number: int
    prompt: str
    template_id: str
    scope_type: str
    markdown: str
    sources: list[QuerySourceResponse]
    gaps: list[str]


class DraftListItemResponse(BaseModel):
    id: UUID
    collection_id: UUID | None
    title: str
    prompt: str
    template_id: str
    scope_type: str
    topic: str | None
    knowledge_gap_id: str | None
    version_number: int
    created_at: str
    updated_at: str | None


class DraftListResponse(BaseModel):
    items: list[DraftListItemResponse]
    total: int


class DraftDetailResponse(BaseModel):
    id: UUID
    collection_id: UUID | None
    current_version_id: UUID
    title: str
    prompt: str
    template_id: str
    scope_type: str
    topic: str | None
    knowledge_gap_id: str | None
    scope_metadata: dict[str, object]
    markdown: str
    sources: list[QuerySourceResponse]
    gaps: list[str]
    version_number: int
    created_at: str
    updated_at: str | None


class DraftVersionResponse(BaseModel):
    id: UUID
    draft_id: UUID
    version_number: int
    title: str
    prompt: str
    template_id: str
    scope_type: str
    collection_id: UUID | None
    topic: str | None
    knowledge_gap_id: str | None
    markdown: str
    sources: list[QuerySourceResponse]
    gaps: list[str]
    created_at: str


class DraftVersionListResponse(BaseModel):
    items: list[DraftVersionResponse]
