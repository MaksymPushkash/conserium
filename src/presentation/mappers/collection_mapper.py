from src.application.dtos.collection_dtos import CollectionDTO, CollectionListDTO, CollectionWorkspaceDTO
from src.presentation.schemas.collection import (
    CollectionListResponse,
    CollectionResponse,
    CollectionWorkspaceDocumentResponse,
    CollectionWorkspaceGapResponse,
    CollectionWorkspaceQuestionResponse,
    CollectionWorkspaceResponse,
    CollectionWorkspaceStatsResponse,
    CollectionWorkspaceTopicResponse,
)


def to_collection_response(dto: CollectionDTO) -> CollectionResponse:
    return CollectionResponse(
        id=dto.id,
        user_id=dto.user_id,
        name=dto.name,
        description=dto.description,
        color=dto.color,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_collection_list_response(dto: CollectionListDTO) -> CollectionListResponse:
    return CollectionListResponse(
        items=[to_collection_response(item) for item in dto.items],
        total=dto.total,
        limit=dto.limit,
        offset=dto.offset,
    )


def to_collection_workspace_response(dto: CollectionWorkspaceDTO) -> CollectionWorkspaceResponse:
    return CollectionWorkspaceResponse(
        collection=to_collection_response(dto.collection),
        stats=CollectionWorkspaceStatsResponse(
            total_documents=dto.stats.total_documents,
            ready_documents=dto.stats.ready_documents,
            processing_documents=dto.stats.processing_documents,
            failed_documents=dto.stats.failed_documents,
            topic_count=dto.stats.topic_count,
            recent_question_count=dto.stats.recent_question_count,
        ),
        documents=[
            CollectionWorkspaceDocumentResponse(
                id=document.id,
                title=document.title,
                type=document.type,
                status=document.status,
                summary=document.summary,
                tags=document.tags,
                activity_temperature=document.activity_temperature,
                created_at=document.created_at,
                updated_at=document.updated_at,
            )
            for document in dto.documents
        ],
        topics=[
            CollectionWorkspaceTopicResponse(
                name=topic.name,
                document_count=topic.document_count,
                last_document_at=topic.last_document_at,
            )
            for topic in dto.topics
        ],
        gaps=[
            CollectionWorkspaceGapResponse(title=gap.title, reason=gap.reason, severity=gap.severity)
            for gap in dto.gaps
        ],
        recent_questions=[
            CollectionWorkspaceQuestionResponse(
                query_text=question.query_text,
                answer_preview=question.answer_preview,
                result_count=question.result_count,
                created_at=question.created_at,
            )
            for question in dto.recent_questions
        ],
    )
