from src.application.dtos.document_dtos import DocumentDTO
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import DocumentAccessDeniedException


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
        is_duplicate=document.is_duplicate,
        duplicate_of_id=document.duplicate_of_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def ensure_document_owner(document: DocumentEntity, user_id: object) -> None:
    if document.user_id != user_id:
        raise DocumentAccessDeniedException("document access denied")
