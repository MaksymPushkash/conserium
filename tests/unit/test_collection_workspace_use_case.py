from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest

from src.application.dtos.compare_dtos import CompareResultDTO
from src.application.ports.persistence.draft_repository import DraftRecord
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
    uow.draft_repo.records = [_draft(user_id=user_id, collection_id=collection.id)]
    uow.compare_repo.records = [_comparison(user_id=user_id, collection_id=collection.id)]

    result = await GetCollectionWorkspaceUseCase(cast("IUnitOfWork", uow))(user_id=user_id, collection_id=collection.id)

    assert result.collection.id == collection.id
    assert result.stats.total_documents == 2
    assert result.stats.ready_documents == 1
    assert result.stats.failed_documents == 1
    assert [topic.name for topic in result.topics] == ["backend", "queues"]
    assert result.recent_questions[0].query_text == "How does queueing work?"
    assert result.recent_drafts[0].title == "Brief: Queues"
    assert result.recent_comparisons[0].summary == "Architecture vs Broken PDF."
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
        self.draft_repo = _DraftRepo()
        self.compare_repo = _CompareRepo()

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

    async def count_by_status(
        self,
        user_id: UUID,
        *,
        collection_id: UUID | None = None,
    ) -> dict[DocumentStatus, int]:
        counts: dict[DocumentStatus, int] = {}
        for document in self._documents:
            if document.user_id == user_id and document.collection_id == collection_id:
                counts[document.status] = counts.get(document.status, 0) + 1
        return counts

    async def get_collection_documents_with_status_counts(
        self,
        user_id: UUID,
        *,
        collection_id: UUID,
        limit: int = 200,
    ) -> tuple[list[DocumentEntity], dict[DocumentStatus, int]]:
        return (
            await self.get_by_user_id(user_id, collection_id=collection_id, limit=limit),
            await self.count_by_status(user_id, collection_id=collection_id),
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


class _DraftRepo:
    def __init__(self) -> None:
        self.records: list[DraftRecord] = []

    async def list_by_user_id(
        self,
        *,
        user_id: UUID,
        collection_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[DraftRecord]:
        records = [
            record
            for record in self.records
            if record.user_id == user_id and (collection_id is None or record.collection_id == collection_id)
        ]
        return records[offset : offset + limit]


class _CompareRepo:
    def __init__(self) -> None:
        self.records: list[CompareResultDTO] = []

    async def list_by_user_id(
        self,
        *,
        user_id: UUID,
        collection_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[CompareResultDTO]:
        records = [
            record
            for record in self.records
            if record.user_id == user_id and (collection_id is None or record.collection_id == collection_id)
        ]
        return records[offset : offset + limit]


def _draft(*, user_id: UUID, collection_id: UUID) -> DraftRecord:
    return DraftRecord(
        id=uuid4(),
        user_id=user_id,
        collection_id=collection_id,
        title="Brief: Queues",
        prompt="Write about queues",
        template_id="brief",
        scope_type="collection",
        topic="queues",
        knowledge_gap_id=None,
        scope_metadata={},
        markdown="# Queues",
        sources=[],
        gaps=[],
        current_version_id=uuid4(),
        version_number=1,
        created_at=datetime(2026, 5, 24, tzinfo=UTC),
        updated_at=None,
    )


def _comparison(*, user_id: UUID, collection_id: UUID) -> CompareResultDTO:
    return CompareResultDTO(
        id=uuid4(),
        user_id=user_id,
        collection_id=collection_id,
        left_document_id=uuid4(),
        right_document_id=uuid4(),
        left_title="Architecture",
        right_title="Broken PDF",
        dimensions=["claims"],
        markdown="## Summary",
        summary="Architecture vs Broken PDF.",
        evidence_rows=[],
        sources=[],
        created_at=datetime(2026, 5, 25, tzinfo=UTC),
    )
