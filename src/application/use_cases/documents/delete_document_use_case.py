from src.application.dtos.document_dtos import DeleteDocumentDTO
from src.application.interfaces.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.base import ensure_document_owner
from src.domain.exceptions import DocumentNotFoundException


class DeleteDocumentUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: DeleteDocumentDTO) -> None:
        async with self._uow:
            document = await self._uow.document_repo.get_by_id(dto.document_id)
            if document is None:
                raise DocumentNotFoundException("document not found")

            ensure_document_owner(document, dto.user_id)
            await self._uow.document_repo.delete(dto.document_id)
            await self._uow.commit()
