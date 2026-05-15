from typing import TYPE_CHECKING, cast

from src.application.dtos.document_dtos import DocumentDTO
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import DocumentAccessDeniedException, ResourceNotFoundException

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.ports.persistence.unit_of_work import IUnitOfWork


def document_to_dto(document: DocumentEntity) -> DocumentDTO:
    return DocumentDTO(
        id=document.id,
        user_id=document.user_id,
        collection_id=document.collection_id,
        title=document.title,
        type=document.type,
        status=document.status,
        source_url=document.source_url,
        file_path=document.file_path,
        file_size_bytes=document.file_size_bytes,
        raw_content=document.raw_content,
        summary=document.summary,
        word_count=document.word_count,
        language=document.language,
        entities=document.entities,
        categories=document.categories,
        visual_metadata=document.visual_metadata,
        suggested_questions=document.suggested_questions,
        tags=document.tags,
        is_duplicate=document.is_duplicate,
        duplicate_of_id=document.duplicate_of_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def ensure_document_owner(document: DocumentEntity, user_id: object) -> None:
    if document.user_id != user_id:
        raise DocumentAccessDeniedException("document access denied")


async def ensure_collection_owner(uow: "IUnitOfWork", collection_id: object, user_id: object) -> None:
    if collection_id is None:
        return
    collection_repo = uow.collection_repo
    collection = await collection_repo.get_by_id(cast("UUID", collection_id))
    if collection is None or collection.user_id != user_id:
        raise ResourceNotFoundException("collection not found")
