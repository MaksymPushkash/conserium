from uuid import UUID

from src.documents.activity_repository import DocumentActivityRepository
from src.query.schemas import QuerySourceDTO


async def record_document_activity(
    document_activity_repo: DocumentActivityRepository,
    user_id: UUID,
    sources: list[QuerySourceDTO],
) -> None:
    queried_document_ids = {source.document_id for source in sources}
    cited_document_ids = {source.document_id for source in sources if source.used_in_answer}
    for document_id in queried_document_ids:
        await document_activity_repo.record_event(
            user_id=user_id,
            document_id=document_id,
            event_type="queried",
        )
    for document_id in cited_document_ids:
        await document_activity_repo.record_event(
            user_id=user_id,
            document_id=document_id,
            event_type="cited_in_answer",
        )
