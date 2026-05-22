from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest

from src.application.ports.persistence.search_query_repository import SearchQuerySummaryRecord
from src.application.use_cases.documents.collection_use_cases import GetCollectionWorkspaceUseCase
from src.domain.entities.collection_entity import CollectionEntity
from src.domain.entities.document_entity import DocumentEntity
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.persistence.document_activity_repository import DocumentActivitySummary
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.domain.value_objects.document_status import DocumentStatus


@pytest.mark.asyncio
async def test_collection_workspace_returns_scoped_overview() -> None:
    user_id = uuid4()
    collection = _collection(user_id)
    ready_document = _document(user_id=user_id, collection_id=collection.id, title="Architecture", tags=["backend", "queues"])
    ready_document.mark_ready()
    failed_document = _document(user_id=user_id, collection_id=collection.id, title="Broken PDF", tags=["backend"])
    failed_document.mark_failed()
    uow = _WorkspaceUow(collection, [ready_document, failed_document])
    uow.search_query_repo.records = [
        SearchQuerySummaryRecord(
            query_text="How does queueing work?",
            answer_text="Use an outbox and worker.",
            result_count=2,
            created_at=datetime(2026, 5, 22, tzinfo=UTC),
        )
    ]

    result = await GetCollectionWorkspaceUseCase(cast("IUnitOfWork", uow))(user_id=user_id, collection_id=collection.id)

    assert result.collection.id == collection.id
    assert result.stats.total_documents == 2
    assert result.stats.ready_documents == 1
    assert result.stats.failed_documents == 1
    assert [topic.name for topic in result.topics] == ["backend", "queues"]
    assert result.recent_questions[0].query_text == "How does queueing work?"
    assert any(gap.title == "Failed processing" for gap in result.gaps)


def _collection(user_id: UUID) -> CollectionEntity:
    return CollectionEntity.create(
        id=uuid4(),
        user_id=user_id,
        name="Backend",
        description="Backend notes",
        color=None,
    )


def _document(*, user_id: UUID, collection_id: UUID, title: str, tags: list[str]) -> DocumentEntity:
    document = DocumentEntity.create(
        id=uuid4(),
        user_id=user_id,
        collection_id=collection_id,
        title=title,
        type=DocumentType.MARKDOWN,
        raw_content="content",
        summary=f"{title} summary",
        word_count=1,
        language="en",
    )
    document.update_enrichment(tags=tags)
    return document


class _WorkspaceUow:
    def __init__(self, collection: CollectionEntity, documents: list[DocumentEntity]) -> None:
        self.collection_repo = _CollectionRepo(collection)
        self.document_repo = _DocumentRepo(documents)
        self.document_activity_repo = _ActivityRepo()
        self.search_query_repo = _SearchQueryRepo()

    async def __aenter__(self) -> _WorkspaceUow:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def commit(self) -> None:
        pass


class _CollectionRepo:
    def __init__(self, collection: CollectionEntity) -> None:
        self._collection = collection

    async def get_by_id(self, collection_id: UUID) -> CollectionEntity | None:
        return self._collection if collection_id == self._collection.id else None


class _DocumentRepo:
    def __init__(self, documents: list[DocumentEntity]) -> None:
        self._documents = documents

    async def get_by_user_id(
        self,
        user_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        document_type: object | None = None,
        collection_id: UUID | None = None,
        status: DocumentStatus | None = None,
    ) -> list[DocumentEntity]:
        documents = [
            document
            for document in self._documents
            if document.user_id == user_id
            and document.collection_id == collection_id
            and (status is None or document.status == status)
        ]
        return documents[offset : offset + limit]

    async def count_by_user_id(
        self,
        user_id: UUID,
        *,
        document_type: object | None = None,
        collection_id: UUID | None = None,
        status: DocumentStatus | None = None,
    ) -> int:
        return len(
            [
                document
                for document in self._documents
                if document.user_id == user_id
                and document.collection_id == collection_id
                and (status is None or document.status == status)
            ]
        )


class _ActivityRepo:
    async def summarize_by_document_ids(
        self,
        *,
        user_id: UUID,
        document_ids: list[UUID],
    ) -> dict[UUID, DocumentActivitySummary]:
        return {}


class _SearchQueryRepo:
    def __init__(self) -> None:
        self.records: list[SearchQuerySummaryRecord] = []

    async def list_recent_by_collection(
        self,
        *,
        user_id: UUID,
        collection_id: UUID,
        limit: int,
    ) -> list[SearchQuerySummaryRecord]:
        return self.records[:limit]
