from src.application.dtos.document_dtos import DocumentListDTO, ListDocumentsDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork
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
                collection_id=dto.collection_id,
                status=dto.status,
            )
            activity = await self._uow.document_activity_repo.summarize_by_document_ids(
                user_id=dto.user_id,
                document_ids=[document.id for document in documents],
            )
            total = await self._uow.document_repo.count_by_user_id(
                dto.user_id,
                collection_id=dto.collection_id,
                status=dto.status,
            )

        return DocumentListDTO(
            items=[document_to_dto(document, activity.get(document.id)) for document in documents],
            total=total,
            limit=dto.limit,
            offset=dto.offset,
        )
