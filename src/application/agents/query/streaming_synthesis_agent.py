from collections.abc import AsyncIterator

from src.application.agents.query.state import CortexQueryState
from src.application.ports.ai.llm_service import IStreamingLLMService


class StreamingSynthesisAgent:
    def __init__(self, llm_service: IStreamingLLMService) -> None:
        self._llm_service = llm_service

    def stream(self, state: CortexQueryState) -> AsyncIterator[str]:
        if state.refrag_context is None:
            raise ValueError("refrag_context is required before streaming synthesis")
        return self._llm_service.stream_answer(query=state.query, context=state.refrag_context)
