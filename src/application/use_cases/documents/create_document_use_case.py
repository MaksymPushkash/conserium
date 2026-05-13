import uuid

from src.application.dtos.document_dtos import CreateDocumentDTO, DocumentDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.base import document_to_dto, ensure_collection_owner
from src.domain.entities.document_entity import DocumentEntity


class CreateDocumentUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: CreateDocumentDTO) -> DocumentDTO:
        async with self._uow:
            await ensure_collection_owner(self._uow, dto.collection_id, dto.user_id)

        document = DocumentEntity.create(
            id=uuid.uuid4(),
            user_id=dto.user_id,
            collection_id=dto.collection_id,
            title=dto.title,
            type=dto.type,
            source_url=dto.source_url,
            file_path=dto.file_path,
            file_size_bytes=dto.file_size_bytes,
            raw_content=dto.raw_content,
            summary=dto.summary,
            word_count=dto.word_count,
            language=dto.language,
        )

        async with self._uow:
            await self._uow.document_repo.create(document)
            await self._uow.commit()

        return document_to_dto(document)
