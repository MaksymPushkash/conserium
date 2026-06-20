from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest

from src.collections.repository import (
    CollectionRepository,
    CollectionWorkspaceRecentActivity,
    CollectionWorkspaceRepository,
)
from src.collections.service import CollectionService
from src.compare.schemas import CompareResultDTO
from src.documents.activity_repository import DocumentActivityRepository
from src.documents.document_repository import DocumentRepository
from src.documents.types import DocumentType
from src.drafts.repository import DraftRecord
from src.models.collection import CollectionModel
from src.models.document import DocumentModel
from src.query.repository import SearchQuerySummaryRecord

if TYPE_CHECKING:
    from src.documents.repository import DocumentActivitySummary
    from src.documents.status import DocumentStatus
    from src.postgres import AsyncSession


@pytest.mark.asyncio
async def test_collection_workspace_returns_scoped_overview(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    collection = _collection(user_id)
    ready_document = _document(user_id=user_id, collection_id=collection.id, title="Architecture", tags=["backend", "queues"])
    ready_document.mark_ready()
    failed_document = _document(user_id=user_id, collection_id=collection.id, title="Broken PDF", tags=["backend"])
    failed_document.mark_failed()
    repositories = _WorkspaceRepositories(collection, [ready_document, failed_document])
    repositories.search_query_repo.records = [
        SearchQuerySummaryRecord(
            query_text="How does queueing work?",
            answer_text="Use an outbox and worker.",
            result_count=2,
            created_at=datetime(2026, 5, 22, tzinfo=UTC),
        )
    ]
    repositories.draft_repo.records = [_draft(user_id=user_id, collection_id=collection.id)]
    repositories.compare_repo.records = [_comparison(user_id=user_id, collection_id=collection.id)]

    monkeypatch.setattr(CollectionRepository, "from_session", classmethod(lambda cls, session: repositories.collection_repo))
    monkeypatch.setattr(DocumentRepository, "from_session", classmethod(lambda cls, session: repositories.document_repo))
    monkeypatch.setattr(
        DocumentActivityRepository,
        "from_session",
        classmethod(lambda cls, session: repositories.document_activity_repo),
    )
    monkeypatch.setattr(
        CollectionWorkspaceRepository,
        "from_session",
        classmethod(lambda cls, session: repositories.collection_workspace_repo),
    )

    result = await CollectionService().workspace(
        cast("AsyncSession", object()),
        user_id=user_id,
        collection_id=collection.id,
    )

    assert result.collection.id == collection.id
    assert result.stats.total_documents == 2
    assert result.stats.ready_documents == 1
    assert result.stats.failed_documents == 1
    assert [topic.name for topic in result.topics] == ["backend", "queues"]
    assert result.recent_questions[0].query_text == "How does queueing work?"
    assert result.recent_drafts[0].title == "Brief: Queues"
    assert result.recent_comparisons[0].summary == "Architecture vs Broken PDF."
    assert any(gap.title == "Failed processing" for gap in result.gaps)


def _collection(user_id: UUID) -> CollectionModel:
    return CollectionModel.create(
        id=uuid4(),
        user_id=user_id,
        name="Backend",
        description="Backend notes",
        color=None,
    )


def _document(*, user_id: UUID, collection_id: UUID, title: str, tags: list[str]) -> DocumentModel:
    document = DocumentModel.create(
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


class _WorkspaceRepositories:
    def __init__(self, collection: CollectionModel, documents: list[DocumentModel]) -> None:
        self.collection_repo = _CollectionRepo(collection)
        self.collection_workspace_repo = _CollectionWorkspaceRepo()
        self.document_repo = _DocumentRepo(documents)
        self.document_activity_repo = _ActivityRepo()
        self.search_query_repo = self.collection_workspace_repo.search_query_repo
        self.draft_repo = self.collection_workspace_repo.draft_repo
        self.compare_repo = self.collection_workspace_repo.compare_repo


class _CollectionRepo:
    def __init__(self, collection: CollectionModel) -> None:
        self._collection = collection

    async def get_by_id(self, collection_id: UUID) -> CollectionModel | None:
        return self._collection if collection_id == self._collection.id else None


class _DocumentRepo:
    def __init__(self, documents: list[DocumentModel]) -> None:
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
    ) -> list[DocumentModel]:
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
    ) -> tuple[list[DocumentModel], dict[DocumentStatus, int]]:
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


class _CollectionWorkspaceRepo:
    def __init__(self) -> None:
        self.search_query_repo = _SearchQueryRepo()
        self.draft_repo = _DraftRepo()
        self.compare_repo = _CompareRepo()

    async def get_recent_activity(
        self,
        *,
        user_id: UUID,
        collection_id: UUID,
        limit: int,
    ) -> CollectionWorkspaceRecentActivity:
        return CollectionWorkspaceRecentActivity(
            questions=await self.search_query_repo.list_recent_by_collection(
                user_id=user_id,
                collection_id=collection_id,
                limit=limit,
            ),
            drafts=await self.draft_repo.list_by_user_id(
                user_id=user_id,
                collection_id=collection_id,
                limit=limit,
            ),
            comparisons=await self.compare_repo.list_by_user_id(
                user_id=user_id,
                collection_id=collection_id,
                limit=limit,
            ),
        )


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
