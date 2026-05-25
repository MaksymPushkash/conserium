from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.value_objects.document_type import DocumentType


@dataclass(frozen=True, slots=True)
class KnowledgeGraphRecord:
    document_id: UUID
    document_title: str
    document_type: str
    topic_name: str
    collection_id: UUID | None = None
    summary: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    suggested_questions: list[str] | None = None
    source_topic_name: str | None = None
    topic_pinned: bool = False
    topic_ignored: bool = False


@dataclass(frozen=True, slots=True)
class KnowledgeEdgeRecord:
    source_document_id: UUID
    target_document_id: UUID
    relation_type: str
    score: float
    evidence: list[str]


@dataclass(frozen=True, slots=True)
class KnowledgeGraphConcernRecord:
    id: UUID
    user_id: UUID
    node_id: str | None
    node_kind: str | None
    node_label: str | None
    message: str
    status: str
    created_at: datetime


class IKnowledgeGraphRepository(ABC):
    @abstractmethod
    async def list_topic_document_links(
        self,
        user_id: UUID,
        *,
        document_limit: int,
        topic_limit: int,
        collection_id: UUID | None = None,
        tag_name: str | None = None,
        topic_name: str | None = None,
        document_type: DocumentType | None = None,
        recency_days: int | None = None,
    ) -> list[KnowledgeGraphRecord]: ...

    @abstractmethod
    async def list_edges(self, user_id: UUID) -> list[KnowledgeEdgeRecord]: ...

    @abstractmethod
    async def replace_edges(self, user_id: UUID, edges: list[KnowledgeEdgeRecord]) -> None: ...

    @abstractmethod
    async def create_concern(
        self,
        *,
        concern_id: UUID,
        user_id: UUID,
        node_id: str | None,
        node_kind: str | None,
        node_label: str | None,
        message: str,
    ) -> KnowledgeGraphConcernRecord: ...
