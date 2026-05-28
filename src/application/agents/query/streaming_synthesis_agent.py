from collections.abc import AsyncIterator

from src.application.agents.query.state import ConseriumQueryState
from src.application.agents.query.synthesis_agent import ABSTENTION_ANSWER, query_with_language_preference
from src.application.ports.ai.llm_service import IStreamingLLMService


class StreamingSynthesisAgent:
    def __init__(self, llm_service: IStreamingLLMService) -> None:
        self._llm_service = llm_service

    def stream(self, state: ConseriumQueryState) -> AsyncIterator[str]:
        if state.refrag_context is None:
            raise ValueError("refrag_context is required before streaming synthesis")
        if not state.refrag_context.selected_chunks:
            return _stream_abstention()
        return self._llm_service.stream_answer(
            query=query_with_language_preference(state.query, state.answer_language),
            context=state.refrag_context,
        )


async def _stream_abstention() -> AsyncIterator[str]:
    yield ABSTENTION_ANSWER
