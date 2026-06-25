from collections.abc import AsyncIterator

from src.kit.ai.llm_service import StreamingLLMService
from src.query.agents.state import ConseriumQueryState
from src.query.agents.synthesis_agent import ABSTENTION_ANSWER, query_with_language_preference


class StreamingSynthesisAgent:
    def __init__(self, llm_service: StreamingLLMService) -> None:
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
