from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.ports.persistence.search_query_repository import ISearchQueryRepository
from src.domain.value_objects.query_type import QueryType
from src.infrastructure.database.models.search_query import SearchQueryModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.application.dtos.evaluation_dtos import QueryEvaluationRecordDTO


class SQLAlchemySearchQueryRepository(ISearchQueryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_query(self, record: QueryEvaluationRecordDTO) -> None:
        self._session.add(
            SearchQueryModel(
                user_id=record.user_id,
                collection_id=record.collection_id,
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


def _to_domain_query_type(query_type: str) -> QueryType:
    if query_type == "summary":
        return QueryType.SUMMARY
    if query_type == "duplicate_check":
        return QueryType.DUPLICATE_CHECK
    return QueryType.SEARCH
