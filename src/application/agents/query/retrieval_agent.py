import re

from src.application.agents.query.state import CortexQueryState
from src.application.ports.ai.reranker import IReranker
from src.application.services.retrieval.chunk_quality_filter import ChunkQualityFilter
from src.application.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from src.core.config import settings
from src.domain.value_objects.document_type import DocumentType


class RetrievalAgent:
    def __init__(
        self,
        retrieval_service: HybridRetrievalService,
        reranker: IReranker | None = None,
        chunk_quality_filter: ChunkQualityFilter | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._reranker = reranker
        self._chunk_quality_filter = chunk_quality_filter or ChunkQualityFilter()

    async def retrieve(self, state: CortexQueryState) -> CortexQueryState:
        retrieval_query = state.retrieval_query or state.query
        document_types = state.document_types or _document_type_filter_for_query(state.query)
        if document_types == (DocumentType.MARKDOWN,):
            retrieval_query = _strip_notes_filter_terms(retrieval_query)
        state.sources = await self._retrieval_service.retrieve(
            query=retrieval_query,
            user_id=state.user_id,
            limit=state.limit,
            collection_id=state.collection_id,
            document_types=document_types,
        )

        if settings.RERANKER_ENABLED and self._reranker is not None and state.sources:
            top_k = min(settings.RERANKER_TOP_K, len(state.sources))
            state.sources = await self._reranker.rerank(state.retrieval_query or state.query, state.sources, top_k)
        state.sources = self._chunk_quality_filter.filter_sources(state.sources)
        if state.promoted_document_ids:
            promoted_ids = set(state.promoted_document_ids)
            state.sources = sorted(
                state.sources,
                key=lambda source: source.document_id not in promoted_ids,
            )
        return state


def _document_type_filter_for_query(query: str) -> tuple[DocumentType, ...] | None:
    normalized = query.casefold()
    if re.search(r"\bnotes?\s+only\b", normalized):
        return (DocumentType.MARKDOWN,)
    if re.search(r"\b(?:from|in|inside)\s+(?:my|me|the)?\s*notes?\b", normalized):
        return (DocumentType.MARKDOWN,)
    if re.search(r"\bmy\s+notes?\b", normalized):
        return (DocumentType.MARKDOWN,)
    return None


def _strip_notes_filter_terms(query: str) -> str:
    cleaned = re.sub(r"\b(?:from|in|inside)\s+(?:my|me|the)?\s*notes?\s*(?:only)?\b", " ", query, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bnotes?\s+only\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bmy\s+notes?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or query
