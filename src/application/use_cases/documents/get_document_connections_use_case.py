from src.application.dtos.document_dtos import DocumentConnectionDTO, DocumentConnectionsDTO, GetDocumentDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.base import document_to_dto, ensure_document_owner
from src.domain.exceptions import DocumentNotFoundException


class GetDocumentConnectionsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: GetDocumentDTO, *, limit: int = 5) -> DocumentConnectionsDTO:
        async with self._uow:
            document = await self._uow.document_repo.get_by_id(dto.document_id)
            if document is None:
                raise DocumentNotFoundException("document not found")
            ensure_document_owner(document, dto.user_id)
            records = await self._uow.document_repo.get_related_documents(
                user_id=dto.user_id,
                document_id=dto.document_id,
                limit=limit,
            )
            activity = await self._uow.document_activity_repo.summarize_by_document_ids(
                user_id=dto.user_id,
                document_ids=[record.document.id for record in records],
            )

        return DocumentConnectionsDTO(
            document_id=dto.document_id,
            total=len(records),
            limit=limit,
            items=[
                DocumentConnectionDTO(
                    document=document_to_dto(record.document, activity.get(record.document.id)),
                    reasons=record.reasons,
                    relationship_score=record.relationship_score,
                )
                for record in records
            ],
        )
