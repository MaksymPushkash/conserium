from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.persistence.stats_repository import IStatsRepository, StatsTimelineBucket
from src.infrastructure.database.models.document import DocumentModel
from src.infrastructure.database.models.document_activity import DocumentActivityModel


class SQLAlchemyStatsRepository(IStatsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_learning_timeline(self, *, user_id: UUID, months: int) -> list[StatsTimelineBucket]:
        month_count = max(1, min(months, 24))
        start_month = shift_month(month_start(datetime.now(UTC)), -(month_count - 1))
        buckets = {
            month_key(shift_month(start_month, index)): {
                "saved_documents": 0,
                "active_documents": 0,
                "query_count": 0,
                "citation_count": 0,
            }
            for index in range(month_count)
        }

        for row in await self._document_rows(user_id=user_id, start_month=start_month):
            buckets[month_key(row.month)]["saved_documents"] = int(row.saved_documents)

        for row in await self._activity_rows(user_id=user_id, start_month=start_month):
            bucket = buckets[month_key(row.month)]
            bucket["active_documents"] = int(row.active_documents)
            bucket["query_count"] = int(row.query_count or 0)
            bucket["citation_count"] = int(row.citation_count or 0)

        return [
            StatsTimelineBucket(
                month=month,
                saved_documents=values["saved_documents"],
                active_documents=values["active_documents"],
                query_count=values["query_count"],
                citation_count=values["citation_count"],
            )
            for month, values in buckets.items()
        ]

    async def _document_rows(self, *, user_id: UUID, start_month: datetime) -> list[Any]:
        month = func.date_trunc("month", DocumentModel.created_at).label("month")
        statement = (
            select(month, func.count(DocumentModel.id).label("saved_documents"))
            .where(DocumentModel.user_id == user_id)
            .where(DocumentModel.created_at >= start_month)
            .group_by(month)
        )
        return list((await self._session.execute(statement)).all())

    async def _activity_rows(self, *, user_id: UUID, start_month: datetime) -> list[Any]:
        month = func.date_trunc("month", DocumentActivityModel.created_at).label("month")
        statement = (
            select(
                month,
                func.count(distinct(DocumentActivityModel.document_id)).label("active_documents"),
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
            .where(DocumentActivityModel.created_at >= start_month)
            .group_by(month)
        )
        return list((await self._session.execute(statement)).all())


def month_start(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def shift_month(value: datetime, offset: int) -> datetime:
    month_index = value.month - 1 + offset
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month)


def month_key(value: datetime) -> str:
    return f"{value.year:04d}-{value.month:02d}"
