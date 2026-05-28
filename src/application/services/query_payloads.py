from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.application.dtos.query_dtos import QueryDebugDTO, QuerySourceDTO

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.agents.query.state import ConseriumQueryState
    from src.application.dtos.refrag_dtos import RefragChunk, RefragContextPackage


def source_payload(source: QuerySourceDTO) -> dict[str, object]:
    return {
        "chunk_id": str(source.chunk_id),
        "document_id": str(source.document_id),
        "document_title": source.document_title,
        "content": source.content,
        "page_number": source.page_number,
        "chunk_index": source.chunk_index,
        "score": source.score,
        "used_in_answer": source.used_in_answer,
    }


def sources_payload(sources: list[QuerySourceDTO]) -> list[dict[str, object]]:
    return [source_payload(source) for source in sources]


def stream_metadata_payload(query_id: UUID, conversation_id: UUID, query: str, sources: list[QuerySourceDTO]) -> dict[str, object]:
    return {
        "query_id": str(query_id),
        "conversation_id": str(conversation_id),
        "query": query,
        "sources": [stream_source_payload(source, index, include_content=False) for index, source in enumerate(sources, start=1)],
    }


def stream_sources_payload(sources: list[QuerySourceDTO]) -> dict[str, object]:
    return {
        "sources": [stream_source_payload(source, index, include_content=True) for index, source in enumerate(sources, start=1)]
    }


def stream_source_payload(source: QuerySourceDTO, citation_index: int, *, include_content: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "citation": f"[{citation_index}]",
        "chunk_id": str(source.chunk_id),
        "document_id": str(source.document_id),
        "document_title": source.document_title,
        "page_number": source.page_number,
        "chunk_index": source.chunk_index,
        "score": source.score,
    }
    if include_content:
        payload["content"] = source.content
        payload["used_in_answer"] = source.used_in_answer
    return payload


def query_debug(original_query: str, state: ConseriumQueryState) -> QueryDebugDTO:
    return QueryDebugDTO(
        original_query=original_query,
        retrieval_query=state.retrieval_query or original_query,
        selected_collection_id=state.collection_id,
        selected_tags=list(state.tag_names or ()),
        promoted_document_ids=list(state.promoted_document_ids),
        retrieved_sources=list(state.retrieved_sources),
        final_sources=list(state.sources),
        used_sources=[source for source in state.sources if source.used_in_answer],
        filtered_sources=list(state.filtered_sources),
    )


def query_debug_payload(original_query: str, state: ConseriumQueryState) -> dict[str, object]:
    debug = query_debug(original_query, state)
    return {
        "original_query": debug.original_query,
        "retrieval_query": debug.retrieval_query,
        "selected_collection_id": str(debug.selected_collection_id) if debug.selected_collection_id else None,
        "selected_tags": debug.selected_tags,
        "promoted_document_ids": [str(document_id) for document_id in debug.promoted_document_ids],
        "retrieved_sources": sources_payload(debug.retrieved_sources),
        "final_sources": sources_payload(debug.final_sources),
        "used_sources": sources_payload(debug.used_sources),
        "filtered_sources": sources_payload(debug.filtered_sources),
    }


def build_follow_up_questions(answer: str, sources: list[QuerySourceDTO]) -> list[str]:
    if not answer.strip() or not any(source.used_in_answer for source in sources):
        return []

    used_sources = [source for source in sources if source.used_in_answer]
    title = next((source.document_title for source in used_sources if source.document_title), None)
    topic = _compact_topic(title or _keywords_from_answer(answer) or "this topic")
    return [
        f"What are the key tradeoffs in {topic}?",
        f"Show the strongest evidence for {topic}.",
        f"What should I read next about {topic}?",
    ]


def refrag_context_payload(context: RefragContextPackage) -> dict[str, object]:
    return {
        "full_text_chunks": [refrag_chunk_payload(chunk) for chunk in context.full_text_chunks],
        "compressed_chunks": [refrag_chunk_payload(chunk) for chunk in context.compressed_chunks],
        "discarded_chunks": [refrag_chunk_payload(chunk) for chunk in context.discarded_chunks],
        "total_original_tokens": context.total_original_tokens,
        "total_context_tokens": context.total_context_tokens,
        "compression_strategy": context.compression_strategy,
    }


def stream_refrag_context_payload(context: RefragContextPackage) -> dict[str, object]:
    return {
        "full_text_chunks": [
            stream_refrag_chunk_payload(chunk, index) for index, chunk in enumerate(context.full_text_chunks, start=1)
        ],
        "compressed_chunks": [
            stream_refrag_chunk_payload(chunk, index)
            for index, chunk in enumerate(context.compressed_chunks, start=len(context.full_text_chunks) + 1)
        ],
        "discarded_chunks": [stream_refrag_chunk_payload(chunk, None) for chunk in context.discarded_chunks],
        "total_original_tokens": context.total_original_tokens,
        "total_context_tokens": context.total_context_tokens,
        "compression_strategy": context.compression_strategy,
    }


def refrag_chunk_payload(chunk: RefragChunk) -> dict[str, object]:
    return {
        "chunk_id": str(chunk.chunk_id),
        "document_id": str(chunk.document_id),
        "document_title": chunk.document_title,
        "representation": chunk.representation.value,
        "page_number": chunk.page_number,
        "chunk_index": chunk.chunk_index,
        "score": chunk.score,
        "context_text": chunk.context_text,
        "original_token_count": chunk.original_token_count,
        "context_token_count": chunk.context_token_count,
    }


def stream_refrag_chunk_payload(chunk: RefragChunk, citation_index: int | None) -> dict[str, object]:
    payload = refrag_chunk_payload(chunk)
    payload["citation"] = f"[{citation_index}]" if citation_index is not None else None
    return payload


def mark_sources_used_in_answer(sources: list[QuerySourceDTO], answer: str) -> list[QuerySourceDTO]:
    used_citations = {int(match) for match in re.findall(r"\[(\d+)\]", answer)}
    return [
        QuerySourceDTO(
            chunk_id=source.chunk_id,
            document_id=source.document_id,
            document_title=source.document_title,
            content=source.content,
            page_number=source.page_number,
            chunk_index=source.chunk_index,
            score=source.score,
            used_in_answer=index in used_citations,
        )
        for index, source in enumerate(sources, start=1)
    ]


def _keywords_from_answer(answer: str) -> str | None:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+-]{3,}", answer)
    ignored = {"this", "that", "with", "from", "have", "about", "there", "their", "which", "would", "should"}
    keywords = [word for word in words if word.lower() not in ignored]
    return " ".join(keywords[:3]) if keywords else None


def _compact_topic(value: str) -> str:
    value = " ".join(value.split())
    return f"{value[:31]}..." if len(value) > 34 else value
