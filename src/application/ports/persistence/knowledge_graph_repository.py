from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class KnowledgeGraphRecord:
    document_id: UUID
    document_title: str
    document_type: str
    topic_name: str


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
