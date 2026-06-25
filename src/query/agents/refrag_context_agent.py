from src.query.agents.state import ConseriumQueryState
from src.query.services.refrag.heuristic_context_builder import HeuristicRefragContextBuilder


class RefragContextAgent:
    def __init__(self, refrag_context_builder: HeuristicRefragContextBuilder) -> None:
        self._refrag_context_builder = refrag_context_builder

    def build_context(self, state: ConseriumQueryState) -> ConseriumQueryState:
        state.refrag_context = self._refrag_context_builder.build_context(
            query=state.query,
            sources=state.sources,
        )
        return state
