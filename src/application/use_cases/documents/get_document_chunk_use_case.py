from src.application.dtos.document_dtos import DocumentChunkDTO, GetDocumentChunkDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.base import ensure_document_owner
from src.domain.exceptions import DocumentNotFoundException


class GetDocumentChunkUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: GetDocumentChunkDTO) -> DocumentChunkDTO:
        async with self._uow:
            document = await self._uow.document_repo.get_by_id(dto.document_id)
            chunk = await self._uow.chunk_repo.get_by_id(dto.chunk_id)

        if document is None:
            raise DocumentNotFoundException("document not found")
        ensure_document_owner(document, dto.user_id)
        if chunk is None or chunk.document_id != dto.document_id:
            raise DocumentNotFoundException("chunk not found")

        return DocumentChunkDTO(
            id=chunk.id,
            document_id=chunk.document_id,
            content=chunk.content,
            chunk_index=chunk.chunk_index,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            page_number=chunk.page_number,
            token_count=chunk.token_count,
        )
