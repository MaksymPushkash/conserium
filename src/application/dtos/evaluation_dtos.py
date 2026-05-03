from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

if TYPE_CHECKING:
    from uuid import UUID


@final
@dataclass(frozen=True, slots=True)
class QueryEvaluationRecordDTO:
    user_id: UUID
    collection_id: UUID | None
    query_text: str
    query_type: str
    result_count: int
    answer_text: str
    latency_ms: int | None
    ragas_faithfulness: float | None
    ragas_answer_relevancy: float | None
    ragas_context_recall: float | None
    langfuse_trace_id: str | None
