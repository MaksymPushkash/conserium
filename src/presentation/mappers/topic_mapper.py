from src.application.dtos.topic_dtos import TopicDetailDTO, TopicListDTO
from src.presentation.schemas.topic import (
    TopicDetailResponse,
    TopicDocumentResponse,
    TopicListResponse,
    TopicResponse,
)


def to_topic_list_response(dto: TopicListDTO) -> TopicListResponse:
    return TopicListResponse(
        items=[
            TopicResponse(
                name=item.name,
                document_count=item.document_count,
                last_document_at=item.last_document_at,
            )
            for item in dto.items
        ],
        total=dto.total,
        limit=dto.limit,
        offset=dto.offset,
    )


def to_topic_detail_response(dto: TopicDetailDTO) -> TopicDetailResponse:
    return TopicDetailResponse(
        topic=TopicResponse(
            name=dto.topic.name,
            document_count=dto.topic.document_count,
            last_document_at=dto.topic.last_document_at,
        ),
        documents=[
            TopicDocumentResponse(
                id=document.id,
                title=document.title,
                type=document.type,
                status=document.status,
                summary=document.summary,
                created_at=document.created_at,
            )
            for document in dto.documents
        ],
    )
