from src.application.agents.query.state import CortexQueryState, QueryType


class RouterAgent:
    def route(self, state: CortexQueryState) -> CortexQueryState:
        normalized_query = state.query.casefold()
        if any(marker in normalized_query for marker in ("summarize", "summary", "підсумуй", "резюме")):
            state.query_type = QueryType.SUMMARY
        elif any(marker in normalized_query for marker in ("this document", "цей документ", "pdf")):
            state.query_type = QueryType.DOCUMENT_QA
        else:
            state.query_type = QueryType.SEARCH
        return state
