from src.application.dtos.document_dtos import DocumentDTO, GetDocumentDTO
from src.application.interfaces.unit_of_work import IUnitOfWork
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
        return document_to_dto(document)
