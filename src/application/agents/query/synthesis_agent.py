from src.application.agents.query.state import CortexQueryState
from src.application.ports.ai.llm_service import ILLMService


class SynthesisAgent:
    def __init__(self, llm_service: ILLMService) -> None:
        self._llm_service = llm_service

    async def synthesize(self, state: CortexQueryState) -> CortexQueryState:
        if state.refrag_context is None:
            raise ValueError("refrag_context is required before synthesis")
        state.answer = await self._llm_service.synthesize_answer(
            query=state.query,
            context=state.refrag_context,
        )
        return state
