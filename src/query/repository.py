from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from src.chats.repository import ChatRepository
from src.models.search_query import SearchQueryModel
from src.query.types import QueryType

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from src.postgres import AsyncSession
    from src.query.schemas import QueryEvaluationRecordDTO


@dataclass(frozen=True, slots=True)
class SearchQuerySummaryRecord:
    query_text: str
    answer_text: str | None
    result_count: int
    created_at: datetime


class SearchQueryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> SearchQueryRepository:
        return cls(session)

    async def record_query(self, record: QueryEvaluationRecordDTO) -> None:
        self._session.add(
            SearchQueryModel(
                user_id=record.user_id,
                collection_id=record.collection_id,
                document_ids=[str(document_id) for document_id in record.document_ids],
                query_text=record.query_text,
                query_type=_to_domain_query_type(record.query_type),
                query_embedding=None,
                result_count=record.result_count,
                answer_text=record.answer_text,
                latency_ms=record.latency_ms,
                ragas_faithfulness=record.ragas_faithfulness,
                ragas_answer_relevancy=record.ragas_answer_relevancy,
                ragas_context_recall=record.ragas_context_recall,
                langfuse_trace_id=record.langfuse_trace_id,
            )
        )

    async def list_recent_by_collection(
        self,
        *,
        user_id: UUID,
        collection_id: UUID,
        limit: int,
    ) -> list[SearchQuerySummaryRecord]:
        result = await self._session.execute(
            select(SearchQueryModel)
            .where(SearchQueryModel.user_id == user_id)
            .where(SearchQueryModel.collection_id == collection_id)
            .order_by(SearchQueryModel.created_at.desc())
            .limit(limit)
        )
        return [
            SearchQuerySummaryRecord(
                query_text=model.query_text,
                answer_text=model.answer_text,
                result_count=model.result_count,
                created_at=model.created_at,
            )
            for model in result.scalars().all()
        ]

    async def list_recent_by_document(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        limit: int,
    ) -> list[SearchQuerySummaryRecord]:
        result = await self._session.execute(
            select(SearchQueryModel)
            .where(SearchQueryModel.user_id == user_id)
            .where(SearchQueryModel.document_ids.contains([str(document_id)]))
            .order_by(SearchQueryModel.created_at.desc())
            .limit(limit)
        )
        return [
            SearchQuerySummaryRecord(
                query_text=model.query_text,
                answer_text=model.answer_text,
                result_count=model.result_count,
                created_at=model.created_at,
            )
            for model in result.scalars().all()
        ]


def _to_domain_query_type(query_type: str) -> QueryType:
    if query_type == "summary":
        return QueryType.SUMMARY
    if query_type == "duplicate_check":
        return QueryType.DUPLICATE_CHECK
    return QueryType.SEARCH


__all__ = [
    "ChatRepository",
    "SearchQueryRepository",
    "SearchQuerySummaryRecord",
]
