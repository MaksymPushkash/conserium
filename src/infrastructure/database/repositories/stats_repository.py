from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.persistence.stats_repository import (
    DailyDigestItemRecord,
    IStatsRepository,
    StatsOverviewRecord,
    StatsTimelineBucket,
    WeeklyReportRecord,
)
from src.domain.value_objects.document_status import DocumentStatus
from src.infrastructure.database.models.document import DocumentModel
from src.infrastructure.database.models.document_activity import DocumentActivityModel


class SQLAlchemyStatsRepository(IStatsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_overview(self, *, user_id: UUID) -> StatsOverviewRecord:
        now = datetime.now(UTC)
        cold_cutoff = now - timedelta(days=14)
        forgotten_cutoff = now - timedelta(days=30)

        last_used = (
            select(
                DocumentModel.id.label("document_id"),
                func.coalesce(func.max(DocumentActivityModel.created_at), DocumentModel.created_at).label("last_used_at"),
            )
            .select_from(DocumentModel)
            .outerjoin(
                DocumentActivityModel,
                (DocumentActivityModel.document_id == DocumentModel.id)
                & (DocumentActivityModel.user_id == user_id),
            )
            .where(DocumentModel.user_id == user_id)
            .group_by(DocumentModel.id, DocumentModel.created_at)
            .subquery()
        )

        total_documents = _document_count(user_id=user_id)
        ready_documents = _document_count(user_id=user_id, status=DocumentStatus.READY)
        failed_documents = _document_count(user_id=user_id, status=DocumentStatus.FAILED)
        pending_documents = _document_count(user_id=user_id, status=DocumentStatus.PENDING)
        queued_documents = _document_count(user_id=user_id, status=DocumentStatus.QUEUED)
        processing_documents = _document_count(user_id=user_id, status=DocumentStatus.PROCESSING)
        query_count = _activity_count(user_id=user_id, event_type="queried")
        citation_count = _activity_count(user_id=user_id, event_type="cited_in_answer")

        statement = select(
            total_documents.label("total_documents"),
            ready_documents.label("ready_documents"),
            (pending_documents + queued_documents + processing_documents).label("processing_documents"),
            failed_documents.label("failed_documents"),
            select(func.count())
            .select_from(last_used)
            .where(last_used.c.last_used_at >= cold_cutoff)
            .scalar_subquery()
            .label("hot_documents"),
            select(func.count())
            .select_from(last_used)
            .where(last_used.c.last_used_at < cold_cutoff)
            .where(last_used.c.last_used_at >= forgotten_cutoff)
            .scalar_subquery()
            .label("cold_documents"),
            select(func.count())
            .select_from(last_used)
            .where(last_used.c.last_used_at < forgotten_cutoff)
            .scalar_subquery()
            .label("forgotten_documents"),
            select(func.count()).select_from(last_used).scalar_subquery().label("active_documents"),
            query_count.label("query_count"),
            citation_count.label("citation_count"),
        )
        row = (await self._session.execute(statement)).one()
        return StatsOverviewRecord(
            total_documents=int(row.total_documents or 0),
            ready_documents=int(row.ready_documents or 0),
            processing_documents=int(row.processing_documents or 0),
            failed_documents=int(row.failed_documents or 0),
            hot_documents=int(row.hot_documents or 0),
            cold_documents=int(row.cold_documents or 0),
            forgotten_documents=int(row.forgotten_documents or 0),
            active_documents=int(row.active_documents or 0),
            query_count=int(row.query_count or 0),
            citation_count=int(row.citation_count or 0),
        )

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

    async def get_daily_digest_items(self, *, user_id: UUID, limit: int = 3) -> list[DailyDigestItemRecord]:
        item_limit = max(1, min(limit, 10))
        now = datetime.now(UTC)
        last_used = (
            select(
                DocumentModel.id.label("document_id"),
                func.coalesce(func.max(DocumentActivityModel.created_at), DocumentModel.created_at).label("last_used_at"),
            )
            .select_from(DocumentModel)
            .outerjoin(
                DocumentActivityModel,
                (DocumentActivityModel.document_id == DocumentModel.id)
                & (DocumentActivityModel.user_id == user_id),
            )
            .where(DocumentModel.user_id == user_id)
            .where(DocumentModel.status == DocumentStatus.READY)
            .group_by(DocumentModel.id, DocumentModel.created_at)
            .subquery()
        )
        statement = (
            select(
                DocumentModel.id,
                DocumentModel.title,
                DocumentModel.summary,
                DocumentModel.suggested_questions,
                last_used.c.last_used_at,
            )
            .join(last_used, last_used.c.document_id == DocumentModel.id)
            .where(DocumentModel.user_id == user_id)
            .order_by(last_used.c.last_used_at.asc())
            .limit(item_limit)
        )
        rows = (await self._session.execute(statement)).all()
        items: list[DailyDigestItemRecord] = []
        for row in rows:
            last_used_at = row.last_used_at
            days_since_activity = max(0, (now - last_used_at).days)
            items.append(
                DailyDigestItemRecord(
                    document_id=row.id,
                    title=row.title,
                    summary=row.summary,
                    question=_digest_question(row.title, row.suggested_questions),
                    reason=f"No activity for {days_since_activity} days.",
                    last_used_at=last_used_at,
                    days_since_activity=days_since_activity,
                )
            )
        return items

    async def get_weekly_report(self, *, user_id: UUID) -> WeeklyReportRecord:
        now = datetime.now(UTC)
        week_cutoff = now - timedelta(days=7)
        stale_cutoff = now - timedelta(days=30)
        last_used = (
            select(
                DocumentModel.id.label("document_id"),
                func.coalesce(func.max(DocumentActivityModel.created_at), DocumentModel.created_at).label("last_used_at"),
            )
            .select_from(DocumentModel)
            .outerjoin(
                DocumentActivityModel,
                (DocumentActivityModel.document_id == DocumentModel.id)
                & (DocumentActivityModel.user_id == user_id),
            )
            .where(DocumentModel.user_id == user_id)
            .group_by(DocumentModel.id, DocumentModel.created_at)
            .subquery()
        )
        statement = select(
            select(func.count(DocumentModel.id))
            .where(DocumentModel.user_id == user_id)
            .where(DocumentModel.created_at >= week_cutoff)
            .scalar_subquery()
            .label("saved_documents"),
            select(func.count(distinct(DocumentActivityModel.document_id)))
            .where(DocumentActivityModel.user_id == user_id)
            .where(DocumentActivityModel.created_at >= week_cutoff)
            .scalar_subquery()
            .label("active_documents"),
            select(func.count(DocumentActivityModel.id))
            .where(DocumentActivityModel.user_id == user_id)
            .where(DocumentActivityModel.created_at >= week_cutoff)
            .where(DocumentActivityModel.event_type == "queried")
            .scalar_subquery()
            .label("query_count"),
            select(func.count(DocumentActivityModel.id))
            .where(DocumentActivityModel.user_id == user_id)
            .where(DocumentActivityModel.created_at >= week_cutoff)
            .where(DocumentActivityModel.event_type == "cited_in_answer")
            .scalar_subquery()
            .label("citation_count"),
            _document_count(user_id=user_id, status=DocumentStatus.READY).label("ready_documents"),
            _document_count(user_id=user_id, status=DocumentStatus.FAILED).label("failed_documents"),
            select(func.count())
            .select_from(last_used)
            .where(last_used.c.last_used_at < stale_cutoff)
            .scalar_subquery()
            .label("stale_documents"),
        )
        row = (await self._session.execute(statement)).one()
        return WeeklyReportRecord(
            saved_documents=int(row.saved_documents or 0),
            active_documents=int(row.active_documents or 0),
            query_count=int(row.query_count or 0),
            citation_count=int(row.citation_count or 0),
            ready_documents=int(row.ready_documents or 0),
            failed_documents=int(row.failed_documents or 0),
            stale_documents=int(row.stale_documents or 0),
        )

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


def _document_count(*, user_id: UUID, status: DocumentStatus | None = None) -> Any:
    statement = select(func.count(DocumentModel.id)).where(DocumentModel.user_id == user_id)
    if status is not None:
        statement = statement.where(DocumentModel.status == status)
    return statement.scalar_subquery()


def _activity_count(*, user_id: UUID, event_type: str) -> Any:
    return (
        select(func.count(DocumentActivityModel.id))
        .where(DocumentActivityModel.user_id == user_id)
        .where(DocumentActivityModel.event_type == event_type)
        .scalar_subquery()
    )


def _digest_question(title: str, suggested_questions: list[str] | None) -> str:
    if suggested_questions:
        for question in suggested_questions:
            if question.strip():
                return question
    return f"What should I remember from {title}?"
