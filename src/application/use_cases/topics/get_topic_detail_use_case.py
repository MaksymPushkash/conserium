from uuid import UUID

from src.application.dtos.topic_dtos import TopicDetailDTO, TopicDocumentDTO, TopicEventDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.topics.topic_mapping import topic_to_dto
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
            events = await self._uow.topic_repo.list_override_events(
                user_id=user_id,
                topic_name=normalized_name,
                limit=10,
            )

        return TopicDetailDTO(
            topic=topic_to_dto(record.topic),
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
            events=tuple(
                TopicEventDTO(
                    action=event.action,
                    topic_name=event.topic_name,
                    display_name=event.display_name,
                    source_names=event.source_names,
                    created_at=event.created_at,
                )
                for event in events
            ),
        )
