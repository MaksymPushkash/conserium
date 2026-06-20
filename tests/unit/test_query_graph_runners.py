import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, cast

from src.query.agents.graph_runner import QueryGraphRunner
from src.query.agents.state import ConseriumQueryState, QueryType
from src.query.agents.streaming_graph_runner import StreamingQueryGraphRunner

if TYPE_CHECKING:
    from src.query.agents.conversation_context_agent import ConversationContextAgent
    from src.query.agents.eval_agent import EvalAgent
    from src.query.agents.refrag_context_agent import RefragContextAgent
    from src.query.agents.retrieval_agent import RetrievalAgent
    from src.query.agents.router_agent import RouterAgent
    from src.query.agents.streaming_synthesis_agent import StreamingSynthesisAgent
    from src.query.agents.synthesis_agent import SynthesisAgent


class _Router:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def route(self, state: ConseriumQueryState) -> ConseriumQueryState:
        self._calls.append("router")
        state.query_type = QueryType.SUMMARY
        return state


class _ConversationContext:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def apply(self, state: ConseriumQueryState) -> ConseriumQueryState:
        self._calls.append("conversation_context")
        state.retrieval_query = f"contextual: {state.query}"
        return state


class _Retrieval:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def retrieve(self, state: ConseriumQueryState) -> ConseriumQueryState:
        self._calls.append("retrieval")
        return state


class _RefragContext:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def build_context(self, state: ConseriumQueryState) -> ConseriumQueryState:
        self._calls.append("refrag_context")
        return state


class _Synthesis:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def synthesize(self, state: ConseriumQueryState) -> ConseriumQueryState:
        self._calls.append("synthesis")
        state.answer = "final answer"
        return state


class _Eval:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def evaluate(self, state: ConseriumQueryState) -> ConseriumQueryState:
        self._calls.append("eval")
        state.eval_scores = {"faithfulness": 1.0, "answer_relevancy": 1.0, "context_recall": 1.0}
        state.trace_id = "trace-1"
        return state


class _StreamingSynthesis:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def _tokens(self) -> AsyncIterator[str]:
        yield "final"

    def stream(self, state: ConseriumQueryState) -> AsyncIterator[str]:
        self._calls.append("streaming_synthesis")
        return self._tokens()


async def test_query_graph_runner_preserves_node_order_and_final_state() -> None:
    calls: list[str] = []
    runner = QueryGraphRunner(
        cast("ConversationContextAgent", _ConversationContext(calls)),
        cast("RouterAgent", _Router(calls)),
        cast("RetrievalAgent", _Retrieval(calls)),
        cast("RefragContextAgent", _RefragContext(calls)),
        cast("SynthesisAgent", _Synthesis(calls)),
        cast("EvalAgent", _Eval(calls)),
    )

    result = await runner.run(
        ConseriumQueryState(
            query="Summarize my notes",
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            limit=5,
        )
    )

    assert calls == ["conversation_context", "router", "retrieval", "refrag_context", "synthesis", "eval"]
    assert result.retrieval_query == "contextual: Summarize my notes"
    assert result.query_type == QueryType.SUMMARY
    assert result.answer == "final answer"
    assert result.trace_id == "trace-1"


async def test_streaming_query_graph_runner_prepare_preserves_node_order_and_streaming_state() -> None:
    calls: list[str] = []
    runner = StreamingQueryGraphRunner(
        cast("ConversationContextAgent", _ConversationContext(calls)),
        cast("RouterAgent", _Router(calls)),
        cast("RetrievalAgent", _Retrieval(calls)),
        cast("RefragContextAgent", _RefragContext(calls)),
        cast("StreamingSynthesisAgent", _StreamingSynthesis(calls)),
        cast("EvalAgent", _Eval(calls)),
    )

    prepared_state = await runner.prepare(
        ConseriumQueryState(
            query="Summarize my notes",
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            limit=5,
        )
    )
    tokens = [token async for token in runner.stream_answer(prepared_state)]

    assert calls == ["conversation_context", "router", "retrieval", "refrag_context", "streaming_synthesis"]
    assert prepared_state.retrieval_query == "contextual: Summarize my notes"
    assert prepared_state.query_type == QueryType.SUMMARY
    assert tokens == ["final"]

    evaluated_state = await runner.evaluate(prepared_state)
    assert evaluated_state.trace_id == "trace-1"
