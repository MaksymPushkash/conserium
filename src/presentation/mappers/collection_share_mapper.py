from src.application.dtos.collection_share_dtos import (
    CollectionShareDTO,
    PublicCollectionDocumentDTO,
    PublicCollectionDTO,
)
from src.presentation.schemas.collection_share import (
    CollectionShareResponse,
    PublicCollectionDocumentResponse,
    PublicCollectionResponse,
)


def to_collection_share_response(dto: CollectionShareDTO) -> CollectionShareResponse:
    return CollectionShareResponse(
        id=dto.id,
        collection_id=dto.collection_id,
        slug=dto.slug,
        include_summaries=dto.include_summaries,
        include_notes=dto.include_notes,
        revoked_at=dto.revoked_at,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_public_collection_response(dto: PublicCollectionDTO) -> PublicCollectionResponse:
    return PublicCollectionResponse(
        id=dto.id,
        name=dto.name,
        description=dto.description,
        color=dto.color,
        documents=[to_public_collection_document_response(document) for document in dto.documents],
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_public_collection_document_response(dto: PublicCollectionDocumentDTO) -> PublicCollectionDocumentResponse:
    return PublicCollectionDocumentResponse(
        id=dto.id,
        title=dto.title,
        type=dto.type,
        status=dto.status,
        source_url=dto.source_url,
        summary=dto.summary,
        word_count=dto.word_count,
        language=dto.language,
        tags=dto.tags,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )
