import uuid
from typing import TYPE_CHECKING, cast

from src.application.agents.query.eval_agent import EvalAgent
from src.application.agents.query.state import CortexQueryState
from src.application.dtos.refrag_dtos import RefragChunk, RefragContextPackage, RefragRepresentation
from src.core.metrics import metrics_registry

if TYPE_CHECKING:
    from src.application.ports.evaluation.eval_scorer import IEvalScorer
    from src.application.ports.observability.query_trace import IQueryTracer


class _EvalScorer:
    async def score(
        self,
        *,
        query: str,
        answer: str,
        context: RefragContextPackage,
    ) -> dict[str, float]:
        return {"faithfulness": 0.9, "answer_relevancy": 0.8, "context_recall": 0.7}


class _QueryTracer:
    async def trace_query(self, state: CortexQueryState) -> str:
        return "trace-123"


class _FailingQueryTracer:
    async def trace_query(self, state: CortexQueryState) -> str:
        raise RuntimeError("tracing unavailable")


def _make_context() -> RefragContextPackage:
    chunk = RefragChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Architecture Notes",
        original_text="Clean Architecture keeps dependencies inward.",
        context_text="Clean Architecture keeps dependencies inward.",
        representation=RefragRepresentation.FULL_TEXT,
        page_number=1,
        chunk_index=0,
        score=0.9,
        original_token_count=5,
        context_token_count=5,
    )
    return RefragContextPackage(
        query="Clean Architecture",
        full_text_chunks=[chunk],
        compressed_chunks=[],
        discarded_chunks=[],
        total_original_tokens=5,
        total_context_tokens=5,
        compression_strategy="test",
    )


async def test_eval_agent_records_scores_trace_id_and_metrics() -> None:
    metrics_registry.reset_for_tests()
    state = CortexQueryState(
        query="Clean Architecture",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
        refrag_context=_make_context(),
        answer="Clean Architecture keeps dependencies inward.",
    )

    result = await EvalAgent(cast("IEvalScorer", _EvalScorer()), cast("IQueryTracer", _QueryTracer())).evaluate(state)

    assert result.eval_scores == {"faithfulness": 0.9, "answer_relevancy": 0.8, "context_recall": 0.7}
    assert result.trace_id == "trace-123"

    metrics_body = metrics_registry.render_prometheus()
    assert "# HELP cortex_query_eval_score Query evaluation score values." in metrics_body
    assert 'cortex_query_eval_score_sum{query_type="search",score="faithfulness"} 0.9' in metrics_body
    assert 'cortex_query_eval_score_count{query_type="search",score="faithfulness"} 1' in metrics_body
    assert 'cortex_query_eval_score_sum{query_type="search",score="answer_relevancy"} 0.8' in metrics_body
    assert 'cortex_query_eval_score_sum{query_type="search",score="context_recall"} 0.7' in metrics_body


async def test_eval_agent_keeps_scores_when_tracing_fails() -> None:
    state = CortexQueryState(
        query="Clean Architecture",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        limit=5,
        refrag_context=_make_context(),
        answer="Clean Architecture keeps dependencies inward.",
    )

    result = await EvalAgent(cast("IEvalScorer", _EvalScorer()), cast("IQueryTracer", _FailingQueryTracer())).evaluate(state)

    assert result.eval_scores == {"faithfulness": 0.9, "answer_relevancy": 0.8, "context_recall": 0.7}
    assert result.trace_id is None
