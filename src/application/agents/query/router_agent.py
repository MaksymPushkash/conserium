import re

from src.application.agents.query.state import CortexQueryState, QueryType

SUMMARY_PATTERN = re.compile(r"\b(summarize|summary|підсумуй|резюме)\b", re.IGNORECASE)
DOCUMENT_QA_PATTERN = re.compile(r"\b(this document|цей документ|pdf)\b", re.IGNORECASE)


class RouterAgent:
    def route(self, state: CortexQueryState) -> CortexQueryState:
        if SUMMARY_PATTERN.search(state.query):
            state.query_type = QueryType.SUMMARY
        elif DOCUMENT_QA_PATTERN.search(state.query):
            state.query_type = QueryType.DOCUMENT_QA
        else:
            state.query_type = QueryType.SEARCH
        return state
