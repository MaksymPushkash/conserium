from src.application.dtos.document_dtos import DocumentListDTO, ListDocumentsDTO
from src.application.interfaces.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.base import document_to_dto


class ListDocumentsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: ListDocumentsDTO) -> DocumentListDTO:
        async with self._uow:
            documents = await self._uow.document_repo.get_by_user_id(
                dto.user_id,
                limit=dto.limit,
                offset=dto.offset,
            )
            total = await self._uow.document_repo.count_by_user_id(dto.user_id)

        return DocumentListDTO(
            items=[document_to_dto(document) for document in documents],
            total=total,
            limit=dto.limit,
            offset=dto.offset,
        )
