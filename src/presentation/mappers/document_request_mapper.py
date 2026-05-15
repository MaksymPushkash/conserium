from uuid import UUID

from src.application.dtos.document_dtos import (
    BulkDocumentOperationDTO,
    CreateDocumentDTO,
    DeleteDocumentDTO,
    GetDocumentChunkDTO,
    GetDocumentDTO,
    ListDocumentsDTO,
    MoveDocumentDTO,
    RenameDocumentDTO,
    ReprocessDocumentDTO,
    RetryDocumentDTO,
    SearchDocumentsDTO,
)
from src.application.dtos.ingestion_dtos import IngestDocumentDTO
from src.domain.value_objects.document_status import DocumentStatus
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


def to_list_documents_dto(
    user_id: UUID,
    limit: int,
    offset: int,
    collection_id: UUID | None,
    status: DocumentStatus | None,
) -> ListDocumentsDTO:
    return ListDocumentsDTO(
        user_id=user_id,
        limit=limit,
        offset=offset,
        collection_id=collection_id,
        status=status,
    )


def to_search_documents_dto(
    *,
    user_id: UUID,
    query: str,
    limit: int,
    collection_id: UUID | None,
    status: DocumentStatus | None,
    document_type: DocumentType | None,
    tag_name: str | None,
) -> SearchDocumentsDTO:
    return SearchDocumentsDTO(
        user_id=user_id,
        query=query,
        limit=limit,
        collection_id=collection_id,
        status=status,
        document_type=document_type,
        tag_name=tag_name,
    )


def to_get_document_dto(document_id: UUID, user_id: UUID) -> GetDocumentDTO:
    return GetDocumentDTO(user_id=user_id, document_id=document_id)


def to_get_document_chunk_dto(document_id: UUID, chunk_id: UUID, user_id: UUID) -> GetDocumentChunkDTO:
    return GetDocumentChunkDTO(user_id=user_id, document_id=document_id, chunk_id=chunk_id)


def to_delete_document_dto(document_id: UUID, user_id: UUID) -> DeleteDocumentDTO:
    return DeleteDocumentDTO(user_id=user_id, document_id=document_id)


def to_rename_document_dto(document_id: UUID, title: str, user_id: UUID) -> RenameDocumentDTO:
    return RenameDocumentDTO(user_id=user_id, document_id=document_id, title=title)


def to_move_document_dto(document_id: UUID, collection_id: UUID | None, user_id: UUID) -> MoveDocumentDTO:
    return MoveDocumentDTO(user_id=user_id, document_id=document_id, collection_id=collection_id)


def to_bulk_document_operation_dto(document_ids: list[UUID], user_id: UUID) -> BulkDocumentOperationDTO:
    return BulkDocumentOperationDTO(user_id=user_id, document_ids=document_ids)


def to_retry_document_dto(document_id: UUID, user_id: UUID) -> RetryDocumentDTO:
    return RetryDocumentDTO(user_id=user_id, document_id=document_id)


def to_reprocess_document_dto(document_id: UUID, user_id: UUID) -> ReprocessDocumentDTO:
    return ReprocessDocumentDTO(user_id=user_id, document_id=document_id)


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
