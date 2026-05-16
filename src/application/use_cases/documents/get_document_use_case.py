from src.application.dtos.document_dtos import DocumentDTO, GetDocumentDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.base import document_to_dto, ensure_document_owner
from src.domain.exceptions import DocumentNotFoundException


class GetDocumentUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: GetDocumentDTO) -> DocumentDTO:
        async with self._uow:
            document = await self._uow.document_repo.get_by_id(dto.document_id)
            if document is None:
                raise DocumentNotFoundException("document not found")
            ensure_document_owner(document, dto.user_id)
            await self._uow.document_activity_repo.record_event(
                user_id=dto.user_id,
                document_id=document.id,
                event_type="opened",
            )
            activity = await self._uow.document_activity_repo.summarize_by_document_ids(
                user_id=dto.user_id,
                document_ids=[document.id],
            )
            await self._uow.commit()

        return document_to_dto(document, activity.get(document.id))
