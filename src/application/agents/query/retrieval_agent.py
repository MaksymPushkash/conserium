from src.application.agents.query.state import CortexQueryState
from src.application.services.retrieval.hybrid_retrieval_service import HybridRetrievalService


class RetrievalAgent:
    def __init__(self, retrieval_service: HybridRetrievalService) -> None:
        self._retrieval_service = retrieval_service

    async def retrieve(self, state: CortexQueryState) -> CortexQueryState:
        state.sources = await self._retrieval_service.retrieve(
            query=state.retrieval_query or state.query,
            user_id=state.user_id,
            limit=state.limit,
            collection_id=state.collection_id,
        )
        if state.promoted_document_ids:
            promoted_ids = set(state.promoted_document_ids)
            state.sources = sorted(
                state.sources,
                key=lambda source: source.document_id not in promoted_ids,
            )
        return state
