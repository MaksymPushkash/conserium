from dataclasses import dataclass
from datetime import datetime
from typing import final
from uuid import UUID


@final
@dataclass(frozen=True, slots=True)
class CreateCollectionDTO:
    user_id: UUID
    name: str
    description: str | None = None
    color: str | None = None


@final
@dataclass(frozen=True, slots=True)
class UpdateCollectionDTO:
    user_id: UUID
    collection_id: UUID
    name: str
    description: str | None = None
    color: str | None = None


@final
@dataclass(frozen=True, slots=True)
class DeleteCollectionDTO:
    user_id: UUID
    collection_id: UUID


@final
@dataclass(frozen=True, slots=True)
class ListCollectionsDTO:
    user_id: UUID
    limit: int = 100
    offset: int = 0


@final
@dataclass(frozen=True, slots=True)
class CollectionDTO:
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    color: str | None
    created_at: datetime
    updated_at: datetime | None


@final
@dataclass(frozen=True, slots=True)
class CollectionListDTO:
    items: list[CollectionDTO]
    total: int
    limit: int
    offset: int


@final
@dataclass(frozen=True, slots=True)
class CollectionWorkspaceStatsDTO:
    total_documents: int
    ready_documents: int
    processing_documents: int
    failed_documents: int
    topic_count: int
    recent_question_count: int


@final
@dataclass(frozen=True, slots=True)
class CollectionWorkspaceDocumentDTO:
    id: UUID
    title: str
    type: str
    status: str
    summary: str | None
    tags: list[str]
    activity_temperature: str
    created_at: datetime
    updated_at: datetime | None


@final
@dataclass(frozen=True, slots=True)
class CollectionWorkspaceTopicDTO:
    name: str
    document_count: int
    last_document_at: datetime | None


@final
@dataclass(frozen=True, slots=True)
class CollectionWorkspaceGapDTO:
    title: str
    reason: str
    severity: str


@final
@dataclass(frozen=True, slots=True)
class CollectionWorkspaceQuestionDTO:
    query_text: str
    answer_preview: str | None
    result_count: int
    created_at: datetime


@final
@dataclass(frozen=True, slots=True)
class CollectionWorkspaceDTO:
    collection: CollectionDTO
    stats: CollectionWorkspaceStatsDTO
    documents: list[CollectionWorkspaceDocumentDTO]
    topics: list[CollectionWorkspaceTopicDTO]
    gaps: list[CollectionWorkspaceGapDTO]
    recent_questions: list[CollectionWorkspaceQuestionDTO]
