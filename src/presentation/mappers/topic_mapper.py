from src.application.dtos.topic_dtos import TopicDetailDTO, TopicDTO, TopicListDTO
from src.presentation.schemas.topic import (
    TopicDetailResponse,
    TopicDocumentResponse,
    TopicEventResponse,
    TopicListResponse,
    TopicResponse,
)


def to_topic_response(dto: TopicDTO) -> TopicResponse:
    return TopicResponse(
        name=dto.name,
        document_count=dto.document_count,
        last_document_at=dto.last_document_at,
        source_names=list(dto.source_names),
        pinned=dto.pinned,
        ignored=dto.ignored,
    )


def to_topic_list_response(dto: TopicListDTO) -> TopicListResponse:
    return TopicListResponse(
        items=[
            to_topic_response(item)
            for item in dto.items
        ],
        total=dto.total,
        limit=dto.limit,
        offset=dto.offset,
    )


def to_topic_detail_response(dto: TopicDetailDTO) -> TopicDetailResponse:
    return TopicDetailResponse(
        topic=to_topic_response(dto.topic),
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
        events=[
            TopicEventResponse(
                action=event.action,
                topic_name=event.topic_name,
                display_name=event.display_name,
                source_names=list(event.source_names),
                created_at=event.created_at,
            )
            for event in dto.events
        ],
    )
