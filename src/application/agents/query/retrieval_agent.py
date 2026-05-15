import re

from src.application.agents.query.state import CortexQueryState
from src.application.ports.ai.reranker import IReranker
from src.application.services.retrieval.chunk_quality_filter import ChunkQualityFilter, ChunkRelevanceFilter
from src.application.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from src.core.config import settings
from src.core.metrics import metrics_registry
from src.domain.value_objects.document_type import DocumentType


class RetrievalAgent:
    def __init__(
        self,
        retrieval_service: HybridRetrievalService,
        reranker: IReranker | None = None,
        chunk_quality_filter: ChunkQualityFilter | None = None,
        chunk_relevance_filter: ChunkRelevanceFilter | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._reranker = reranker
        self._chunk_quality_filter = chunk_quality_filter or ChunkQualityFilter()
        self._chunk_relevance_filter = chunk_relevance_filter or ChunkRelevanceFilter()

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
            tag_names=state.tag_names,
            document_types=document_types,
        )
        state.retrieved_sources = list(state.sources)

        if settings.RERANKER_ENABLED and self._reranker is not None and state.sources:
            top_k = min(settings.RERANKER_TOP_K, len(state.sources))
            state.sources = await self._reranker.rerank(state.retrieval_query or state.query, state.sources, top_k)
        quality_sources = self._chunk_quality_filter.filter_sources(state.sources)
        relevance_query = retrieval_query if document_types == (DocumentType.MARKDOWN,) else state.query
        relevant_sources = self._chunk_relevance_filter.filter_sources(relevance_query, quality_sources)
        relevant_keys = {source.chunk_id for source in relevant_sources}
        state.filtered_sources = [source for source in state.sources if source.chunk_id not in relevant_keys]
        state.sources = relevant_sources
        if state.promoted_document_ids:
            promoted_ids = set(state.promoted_document_ids)
            state.sources = sorted(
                state.sources,
                key=lambda source: source.document_id not in promoted_ids,
            )
        metrics_registry.inc_counter(
            "cortex_retrieval_requests_total",
            "Retrieval requests grouped by outcome.",
            labels={"scoped": str(state.collection_id is not None).lower()},
        )
        if state.sources:
            metrics_registry.inc_counter(
                "cortex_retrieval_hits_total",
                "Retrieval requests with at least one usable source.",
                labels={"scoped": str(state.collection_id is not None).lower()},
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
