from collections.abc import AsyncIterator
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.application.agents.query.conversation_context_agent import ConversationContextAgent
from src.application.agents.query.eval_agent import EvalAgent
from src.application.agents.query.refrag_context_agent import RefragContextAgent
from src.application.agents.query.retrieval_agent import RetrievalAgent
from src.application.agents.query.router_agent import RouterAgent
from src.application.agents.query.state import ConseriumQueryState, coerce_conserium_query_state
from src.application.agents.query.streaming_synthesis_agent import StreamingSynthesisAgent


class StreamingQueryGraphRunner:
    def __init__(
        self,
        conversation_context_agent: ConversationContextAgent,
        router_agent: RouterAgent,
        retrieval_agent: RetrievalAgent,
        refrag_context_agent: RefragContextAgent,
        synthesis_agent: StreamingSynthesisAgent,
        eval_agent: EvalAgent,
    ) -> None:
        self._conversation_context_agent = conversation_context_agent
        self._router_agent = router_agent
        self._retrieval_agent = retrieval_agent
        self._refrag_context_agent = refrag_context_agent
        self._synthesis_agent = synthesis_agent
        self._eval_agent = eval_agent
        self._prepare_graph = self._build_prepare_graph()

    async def prepare(self, state: ConseriumQueryState) -> ConseriumQueryState:
        result = await self._prepare_graph.ainvoke(state)
        return coerce_conserium_query_state(result)

    def stream_answer(self, state: ConseriumQueryState) -> AsyncIterator[str]:
        return self._synthesis_agent.stream(state)

    async def evaluate(self, state: ConseriumQueryState) -> ConseriumQueryState:
        return await self._eval_agent.evaluate(state)

    def _build_prepare_graph(self) -> Any:
        graph = StateGraph(ConseriumQueryState)
        graph.add_node("conversation_context", self._apply_conversation_context)
        graph.add_node("router", self._route)
        graph.add_node("retrieval", self._retrieve)
        graph.add_node("refrag_context", self._build_refrag_context)
        graph.add_edge(START, "conversation_context")
        graph.add_edge("conversation_context", "router")
        graph.add_edge("router", "retrieval")
        graph.add_edge("retrieval", "refrag_context")
        graph.add_edge("refrag_context", END)
        return graph.compile()

    def _apply_conversation_context(self, state: ConseriumQueryState) -> ConseriumQueryState:
        return self._conversation_context_agent.apply(state)

    def _route(self, state: ConseriumQueryState) -> ConseriumQueryState:
        return self._router_agent.route(state)

    async def _retrieve(self, state: ConseriumQueryState) -> ConseriumQueryState:
        return await self._retrieval_agent.retrieve(state)

    def _build_refrag_context(self, state: ConseriumQueryState) -> ConseriumQueryState:
        return self._refrag_context_agent.build_context(state)
