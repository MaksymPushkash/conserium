from uuid import UUID

from src.application.dtos.query_dtos import QuerySourceDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork


async def record_document_activity(uow: IUnitOfWork, user_id: UUID, sources: list[QuerySourceDTO]) -> None:
    queried_document_ids = {source.document_id for source in sources}
    cited_document_ids = {source.document_id for source in sources if source.used_in_answer}
    for document_id in queried_document_ids:
        await uow.document_activity_repo.record_event(
            user_id=user_id,
            document_id=document_id,
            event_type="queried",
        )
    for document_id in cited_document_ids:
        await uow.document_activity_repo.record_event(
            user_id=user_id,
            document_id=document_id,
            event_type="cited_in_answer",
        )
