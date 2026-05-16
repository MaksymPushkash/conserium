from uuid import UUID

from src.application.dtos.topic_dtos import TopicDetailDTO, TopicDocumentDTO, TopicDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.domain.exceptions import ResourceNotFoundException


class GetTopicDetailUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, name: str, document_limit: int = 10) -> TopicDetailDTO:
        normalized_name = name.strip().lower()
        async with self._uow:
            record = await self._uow.topic_repo.get_detail_by_name(
                user_id,
                name=normalized_name,
                document_limit=document_limit,
            )
        if record is None:
            raise ResourceNotFoundException("topic not found")

        return TopicDetailDTO(
            topic=TopicDTO(
                name=record.topic.name,
                document_count=record.topic.document_count,
                last_document_at=record.topic.last_document_at,
            ),
            documents=[
                TopicDocumentDTO(
                    id=str(document.id),
                    title=document.title,
                    type=document.type,
                    status=document.status,
                    summary=document.summary,
                    created_at=document.created_at,
                )
                for document in record.documents
            ],
        )
