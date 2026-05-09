from uuid import UUID

from src.application.dtos.document_dtos import CreateDocumentDTO, DeleteDocumentDTO, GetDocumentDTO, ListDocumentsDTO
from src.application.dtos.ingestion_dtos import IngestDocumentDTO
from src.domain.value_objects.document_type import DocumentType
from src.presentation.schemas.document import CreateDocumentRequest, IngestDocumentRequest, IngestTextDocumentRequest


def to_create_document_dto(body: CreateDocumentRequest, user_id: UUID) -> CreateDocumentDTO:
    return CreateDocumentDTO(
        user_id=user_id,
        title=body.title,
        type=body.type,
        collection_id=body.collection_id,
        source_url=body.source_url,
        file_path=body.file_path,
        file_size_bytes=body.file_size_bytes,
        raw_content=body.raw_content,
        summary=body.summary,
        word_count=body.word_count,
        language=body.language,
    )


def to_list_documents_dto(user_id: UUID, limit: int, offset: int) -> ListDocumentsDTO:
    return ListDocumentsDTO(user_id=user_id, limit=limit, offset=offset)


def to_get_document_dto(document_id: UUID, user_id: UUID) -> GetDocumentDTO:
    return GetDocumentDTO(user_id=user_id, document_id=document_id)


def to_delete_document_dto(document_id: UUID, user_id: UUID) -> DeleteDocumentDTO:
    return DeleteDocumentDTO(user_id=user_id, document_id=document_id)


def to_ingest_document_dto(body: IngestDocumentRequest, user_id: UUID) -> IngestDocumentDTO:
    return IngestDocumentDTO(
        user_id=user_id,
        title=body.title,
        type=body.type,
        collection_id=body.collection_id,
        source_url=body.source_url,
        file_path=body.file_path,
        file_size_bytes=body.file_size_bytes,
        raw_content=body.raw_content,
        language=body.language,
    )


def to_ingest_text_document_dto(body: IngestTextDocumentRequest, user_id: UUID) -> IngestDocumentDTO:
    return IngestDocumentDTO(
        user_id=user_id,
        title=body.title,
        type=body.type,
        collection_id=body.collection_id,
        source_url=body.source_url,
        raw_content=body.raw_text,
        language=body.language,
    )


def to_uploaded_ingest_document_dto(
    *,
    user_id: UUID,
    title: str,
    document_type: DocumentType,
    collection_id: UUID | None,
    file_path: str,
    file_size_bytes: int,
    language: str | None,
) -> IngestDocumentDTO:
    return IngestDocumentDTO(
        user_id=user_id,
        title=title,
        type=document_type,
        collection_id=collection_id,
        file_path=file_path,
        file_size_bytes=file_size_bytes,
        language=language,
    )
