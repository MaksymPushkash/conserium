from src.kit.ports.ai.llm_service import ILLMService
from src.query.agents.state import ConseriumQueryState

ABSTENTION_ANSWER = "The provided context does not contain enough relevant information to answer this question."


class SynthesisAgent:
    def __init__(self, llm_service: ILLMService) -> None:
        self._llm_service = llm_service

    async def synthesize(self, state: ConseriumQueryState) -> ConseriumQueryState:
        if state.refrag_context is None:
            raise ValueError("refrag_context is required before synthesis")
        if not state.refrag_context.selected_chunks:
            state.answer = ABSTENTION_ANSWER
            return state
        state.answer = await self._llm_service.synthesize_answer(
            query=query_with_language_preference(state.query, state.answer_language),
            context=state.refrag_context,
        )
        return state


def query_with_language_preference(query: str, answer_language: str) -> str:
    if answer_language == "english":
        return f"{query}\n\nAnswer language: English."
    if answer_language == "ukrainian":
        return f"{query}\n\nAnswer language: Ukrainian."
    return query
