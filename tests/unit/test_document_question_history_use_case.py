import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from src.application.dtos.document_dtos import GetDocumentDTO
from src.application.ports.persistence.search_query_repository import SearchQuerySummaryRecord
from src.application.use_cases.documents.get_document_question_history_use_case import GetDocumentQuestionHistoryUseCase
from src.domain.entities.document_entity import DocumentEntity
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


async def test_document_question_history_lists_recent_document_queries() -> None:
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    created_at = datetime.now(UTC)
    uow = _UnitOfWork(
        DocumentEntity.create(
            id=document_id,
            user_id=user_id,
            title="Architecture notes",
            type=DocumentType.TEXT,
            raw_content="content",
        ),
        [
            SearchQuerySummaryRecord(
                query_text="What are the tradeoffs?",
                answer_text="The tradeoff is latency.",
                result_count=2,
                created_at=created_at,
            )
        ],
    )
    use_case = GetDocumentQuestionHistoryUseCase(cast("IUnitOfWork", uow))

    result = await use_case(GetDocumentDTO(user_id=user_id, document_id=document_id), limit=5)

    assert result.document_id == document_id
    assert result.limit == 5
    assert result.items[0].query_text == "What are the tradeoffs?"
    assert uow.search_query_repo.received_document_id == document_id


class _DocumentRepository:
    def __init__(self, document: DocumentEntity) -> None:
        self._document = document

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentEntity | None:
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


class _UnitOfWork:
    def __init__(self, document: DocumentEntity, records: list[SearchQuerySummaryRecord]) -> None:
        self.document_repo = _DocumentRepository(document)
        self.search_query_repo = _SearchQueryRepository(records)

    async def __aenter__(self) -> "_UnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None
