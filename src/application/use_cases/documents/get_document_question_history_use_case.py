from src.application.dtos.document_dtos import (
    DocumentQuestionHistoryDTO,
    DocumentQuestionHistoryItemDTO,
    GetDocumentDTO,
)
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.base import ensure_document_owner
from src.domain.exceptions import DocumentNotFoundException


class GetDocumentQuestionHistoryUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: GetDocumentDTO, *, limit: int) -> DocumentQuestionHistoryDTO:
        async with self._uow:
            document = await self._uow.document_repo.get_by_id(dto.document_id)
            if document is None:
                raise DocumentNotFoundException("document not found")
            ensure_document_owner(document, dto.user_id)
            records = await self._uow.search_query_repo.list_recent_by_document(
                user_id=dto.user_id,
                document_id=dto.document_id,
                limit=limit,
            )
        return DocumentQuestionHistoryDTO(
            document_id=dto.document_id,
            limit=limit,
            items=[
                DocumentQuestionHistoryItemDTO(
                    query_text=record.query_text,
                    answer_text=record.answer_text,
                    result_count=record.result_count,
                    created_at=record.created_at,
                )
                for record in records
            ],
        )
