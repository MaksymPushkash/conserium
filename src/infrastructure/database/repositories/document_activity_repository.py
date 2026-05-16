from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, func, outerjoin, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.persistence.document_activity_repository import (
    DocumentActivityEventType,
    DocumentActivityOverview,
    DocumentActivitySummary,
    IDocumentActivityRepository,
)
from src.infrastructure.database.models.document import DocumentModel
from src.infrastructure.database.models.document_activity import DocumentActivityModel


class SQLAlchemyDocumentActivityRepository(IDocumentActivityRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_event(self, *, user_id: UUID, document_id: UUID, event_type: DocumentActivityEventType) -> None:
        self._session.add(DocumentActivityModel(user_id=user_id, document_id=document_id, event_type=event_type))

    async def summarize_by_document_ids(
        self,
        *,
        user_id: UUID,
        document_ids: list[UUID],
    ) -> dict[UUID, DocumentActivitySummary]:
        if not document_ids:
            return {}
        statement = (
            select(
                DocumentActivityModel.document_id,
                func.max(DocumentActivityModel.created_at).label("last_used_at"),
                func.coalesce(
                    func.sum(case((DocumentActivityModel.event_type == "queried", 1), else_=0)),
                    0,
                ).label("query_count"),
                func.coalesce(
                    func.sum(case((DocumentActivityModel.event_type == "cited_in_answer", 1), else_=0)),
                    0,
                ).label("citation_count"),
            )
            .where(DocumentActivityModel.user_id == user_id)
            .where(DocumentActivityModel.document_id.in_(document_ids))
            .group_by(DocumentActivityModel.document_id)
        )
        rows = (await self._session.execute(statement)).all()
        return {
            row.document_id: DocumentActivitySummary(
                document_id=row.document_id,
                last_used_at=row.last_used_at,
                query_count=int(row.query_count or 0),
                citation_count=int(row.citation_count or 0),
            )
            for row in rows
        }

    async def summarize_user_overview(self, *, user_id: UUID) -> DocumentActivityOverview:
        last_used_rows = await self._last_used_rows(user_id)
        event_counts = await self._event_counts(user_id)
        temperatures = [_activity_temperature(last_used_at) for last_used_at in last_used_rows]
        return DocumentActivityOverview(
            hot_documents=temperatures.count("hot"),
            cold_documents=temperatures.count("cold"),
            forgotten_documents=temperatures.count("forgotten"),
            active_documents=sum(1 for last_used_at in last_used_rows if last_used_at is not None),
            query_count=event_counts["queried"],
            citation_count=event_counts["cited_in_answer"],
        )

    async def _last_used_rows(self, user_id: UUID) -> list[datetime]:
        statement = (
            select(
                func.coalesce(
                    func.max(DocumentActivityModel.created_at),
                    DocumentModel.created_at,
                ).label("last_used_at")
            )
            .select_from(
                outerjoin(
                    DocumentModel,
                    DocumentActivityModel,
                    (DocumentActivityModel.document_id == DocumentModel.id)
                    & (DocumentActivityModel.user_id == user_id),
                )
            )
            .where(DocumentModel.user_id == user_id)
            .group_by(DocumentModel.id, DocumentModel.created_at)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def _event_counts(self, user_id: UUID) -> dict[str, int]:
        statement = (
            select(
                DocumentActivityModel.event_type,
                func.count(DocumentActivityModel.id),
            )
            .where(DocumentActivityModel.user_id == user_id)
            .where(DocumentActivityModel.event_type.in_(("queried", "cited_in_answer")))
            .group_by(DocumentActivityModel.event_type)
        )
        rows = (await self._session.execute(statement)).all()
        counts = {"queried": 0, "cited_in_answer": 0}
        for event_type, count in rows:
            counts[str(event_type)] = int(count)
        return counts


def _activity_temperature(last_used_at: datetime) -> str:
    age_days = (datetime.now(UTC) - last_used_at).days
    if age_days >= 30:
        return "forgotten"
    if age_days >= 14:
        return "cold"
    return "hot"
