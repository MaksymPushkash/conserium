from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.application.dtos.query_dtos import QuerySourceDTO
from src.domain.value_objects.document_type import DocumentType


@dataclass(frozen=True, slots=True)
class DraftTemplateDTO:
    id: str
    name: str
    description: str
    prompt: str
    outline: list[str]


@dataclass(frozen=True, slots=True)
class DraftGenerateDTO:
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
class DraftResultDTO:
    draft_id: UUID
    version_id: UUID
    version_number: int
    prompt: str
    template_id: str
    scope_type: str
    markdown: str
    sources: list[QuerySourceDTO]
    gaps: list[str]


@dataclass(frozen=True, slots=True)
class DraftOutlineDTO:
    prompt: str
    template_id: str
    scope_type: str
    title: str
    sections: list[str]


@dataclass(frozen=True, slots=True)
class DraftListItemDTO:
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
class DraftListDTO:
    items: list[DraftListItemDTO]
    total: int


@dataclass(frozen=True, slots=True)
class DraftDetailDTO:
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
    sources: list[QuerySourceDTO]
    gaps: list[str]
    version_number: int
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class DraftVersionDTO:
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
    sources: list[QuerySourceDTO]
    gaps: list[str]
    created_at: datetime
