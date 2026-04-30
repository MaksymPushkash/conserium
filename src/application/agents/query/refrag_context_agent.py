from src.application.agents.query.state import CortexQueryState
from src.application.ports.refrag.refrag_context_builder import IRefragContextBuilder


class RefragContextAgent:
    def __init__(self, refrag_context_builder: IRefragContextBuilder) -> None:
        self._refrag_context_builder = refrag_context_builder

    def build_context(self, state: CortexQueryState) -> CortexQueryState:
        state.refrag_context = self._refrag_context_builder.build_context(
            query=state.query,
            sources=state.sources,
        )
        return state
