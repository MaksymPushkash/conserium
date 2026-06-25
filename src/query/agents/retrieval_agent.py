import re

from src.documents.types import DocumentType
from src.observability.metrics_registry import metrics_registry
from src.query.agents.state import ConseriumQueryState
from src.query.schemas import QuerySource
from src.query.services.retrieval.chunk_quality_filter import ChunkQualityFilter, ChunkRelevanceFilter
from src.query.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from src.query.services.retrieval.reranker import Reranker
from src.settings import settings


class RetrievalAgent:
    def __init__(
        self,
        retrieval_service: HybridRetrievalService,
        reranker: Reranker | None = None,
        chunk_quality_filter: ChunkQualityFilter | None = None,
        chunk_relevance_filter: ChunkRelevanceFilter | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._reranker = reranker
        self._chunk_quality_filter = chunk_quality_filter or ChunkQualityFilter()
        self._chunk_relevance_filter = chunk_relevance_filter or ChunkRelevanceFilter()

    async def retrieve(self, state: ConseriumQueryState) -> ConseriumQueryState:
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
            document_ids=state.document_ids,
        )
        state.retrieved_sources = list(state.sources)

        if settings.RERANKER_ENABLED and self._reranker is not None and state.sources:
            top_k = min(settings.RERANKER_TOP_K, len(state.sources))
            state.sources = await self._reranker.rerank(state.retrieval_query or state.query, state.sources, top_k)
        quality_sources = self._chunk_quality_filter.filter_sources(state.sources)
        explicit_relevance_query = state.relevance_query is not None
        relevance_query = state.relevance_query or (retrieval_query if document_types == (DocumentType.MARKDOWN,) else state.query)
        relevant_sources = self._chunk_relevance_filter.filter_sources(relevance_query, quality_sources)
        if explicit_relevance_query or state.document_ids is not None:
            relevant_sources = _merge_relevance_fallbacks(
                relevant_sources,
                quality_sources[: _fallback_source_count(state.limit, document_scoped=state.document_ids is not None)],
            )
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
            "conserium_retrieval_requests_total",
            "Retrieval requests grouped by outcome.",
            labels={"scoped": str(state.collection_id is not None).lower()},
        )
        if state.sources:
            metrics_registry.inc_counter(
                "conserium_retrieval_hits_total",
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


def _fallback_source_count(limit: int, *, document_scoped: bool) -> int:
    if document_scoped:
        return max(4, limit)
    return min(max(3, limit // 2), limit)


def _merge_relevance_fallbacks(primary: list[QuerySource], fallback: list[QuerySource]) -> list[QuerySource]:
    merged = list(primary)
    seen = {source.chunk_id for source in merged}
    for source in fallback:
        if source.chunk_id not in seen:
            merged.append(source)
            seen.add(source.chunk_id)
    return merged
