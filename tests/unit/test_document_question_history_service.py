import uuid
from datetime import UTC, datetime

from src.documents.schemas import GetDocumentDTO
from src.documents.service import DocumentService
from src.documents.types import DocumentType
from src.models.document import DocumentModel
from src.query.repository import SearchQuerySummaryRecord


async def test_document_question_history_lists_recent_document_queries() -> None:
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    created_at = datetime.now(UTC)
    document_repo = _DocumentRepository(
        DocumentModel.create(
            id=document_id,
            user_id=user_id,
            title="Architecture notes",
            type=DocumentType.TEXT,
            raw_content="content",
        ),
    )
    search_query_repo = _SearchQueryRepository(
        [
            SearchQuerySummaryRecord(
                query_text="What are the tradeoffs?",
                answer_text="The tradeoff is latency.",
                result_count=2,
                created_at=created_at,
            )
        ],
    )
    service = DocumentService(  # type: ignore[arg-type]
        object(),
        document_repo,
        object(),
        object(),
        object(),
        object(),
        search_query_repo,
        object(),
        object(),
    )

    result = await service.question_history(GetDocumentDTO(user_id=user_id, document_id=document_id), limit=5)

    assert result.document_id == document_id
    assert result.limit == 5
    assert result.items[0].query_text == "What are the tradeoffs?"
    assert search_query_repo.received_document_id == document_id


class _DocumentRepository:
    def __init__(self, document: DocumentModel) -> None:
        self._document = document

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentModel | None:
        return self._document if self._document.id == document_id else None


class _SearchQueryRepository:
    def __init__(self, records: list[SearchQuerySummaryRecord]) -> None:
        self._records = records
        self.received_document_id: uuid.UUID | None = None

    async def list_recent_by_document(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        limit: int,
    ) -> list[SearchQuerySummaryRecord]:
        self.received_document_id = document_id
        return self._records[:limit]
