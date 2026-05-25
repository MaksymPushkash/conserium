from src.application.dtos.topic_dtos import TopicDTO
from src.application.ports.persistence.topic_repository import TopicRecord


def topic_to_dto(record: TopicRecord) -> TopicDTO:
    return TopicDTO(
        name=record.name,
        document_count=record.document_count,
        last_document_at=record.last_document_at,
        source_names=record.source_names,
        pinned=record.pinned,
        ignored=record.ignored,
    )
