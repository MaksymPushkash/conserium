from src.application.dtos.query_dtos import QueryDebugDTO, QueryResultDTO, QuerySourceDTO
from src.application.dtos.refrag_dtos import RefragChunk, RefragContextPackage
from src.presentation.schemas.query import (
    QueryDebugResponse,
    QueryResponse,
    QuerySourceResponse,
    RefragChunkResponse,
    RefragContextResponse,
)


def to_query_source_response(dto: QuerySourceDTO, index: int) -> QuerySourceResponse:
    return QuerySourceResponse(
        chunk_id=dto.chunk_id,
        document_id=dto.document_id,
        document_title=dto.document_title,
        content=dto.content,
        page_number=dto.page_number,
        chunk_index=dto.chunk_index,
        score=dto.score,
        citation=f"[{index}]",
        used_in_answer=dto.used_in_answer,
    )


def to_refrag_chunk_response(dto: RefragChunk, citation: str | None) -> RefragChunkResponse:
    return RefragChunkResponse(
        chunk_id=dto.chunk_id,
        document_id=dto.document_id,
        document_title=dto.document_title,
        representation=dto.representation,
        page_number=dto.page_number,
        chunk_index=dto.chunk_index,
        score=dto.score,
        context_text=dto.context_text,
        original_token_count=dto.original_token_count,
        context_token_count=dto.context_token_count,
        citation=citation,
    )


def to_refrag_context_response(dto: RefragContextPackage) -> RefragContextResponse:
    full_text_chunks = [
        to_refrag_chunk_response(chunk, f"[{index}]") for index, chunk in enumerate(dto.full_text_chunks, start=1)
    ]
    compressed_start = len(dto.full_text_chunks) + 1
    compressed_chunks = [
        to_refrag_chunk_response(chunk, f"[{index}]")
        for index, chunk in enumerate(dto.compressed_chunks, start=compressed_start)
    ]
    discarded_chunks = [to_refrag_chunk_response(chunk, None) for chunk in dto.discarded_chunks]
    return RefragContextResponse(
        full_text_chunks=full_text_chunks,
        compressed_chunks=compressed_chunks,
        discarded_chunks=discarded_chunks,
        total_original_tokens=dto.total_original_tokens,
        total_context_tokens=dto.total_context_tokens,
        compression_strategy=dto.compression_strategy,
    )


def to_query_response(dto: QueryResultDTO) -> QueryResponse:
    return QueryResponse(
        conversation_id=dto.conversation_id,
        query=dto.query,
        answer=dto.answer,
        sources=[to_query_source_response(source, index) for index, source in enumerate(dto.sources, start=1)],
        refrag_context=to_refrag_context_response(dto.refrag_context),
        debug=to_query_debug_response(dto.debug) if dto.debug else None,
    )


def to_query_debug_response(dto: QueryDebugDTO) -> QueryDebugResponse:
    return QueryDebugResponse(
        original_query=dto.original_query,
        retrieval_query=dto.retrieval_query,
        selected_collection_id=dto.selected_collection_id,
        selected_tags=dto.selected_tags,
        promoted_document_ids=dto.promoted_document_ids,
        retrieved_sources=[
            to_query_source_response(source, index) for index, source in enumerate(dto.retrieved_sources, start=1)
        ],
        final_sources=[to_query_source_response(source, index) for index, source in enumerate(dto.final_sources, start=1)],
        used_sources=[to_query_source_response(source, index) for index, source in enumerate(dto.used_sources, start=1)],
        filtered_sources=[
            to_query_source_response(source, index) for index, source in enumerate(dto.filtered_sources, start=1)
        ],
    )
