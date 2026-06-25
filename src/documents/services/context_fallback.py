from src.query.schemas import QuerySource, RefragChunk, RefragContextPackage, RefragRepresentation


def refrag_context_from_sources(query: str, sources: list[QuerySource]) -> RefragContextPackage:
    chunks = [
        RefragChunk(
            chunk_id=source.chunk_id,
            document_id=source.document_id,
            document_title=source.document_title,
            original_text=source.content,
            context_text=source.content,
            representation=RefragRepresentation.FULL_TEXT,
            page_number=source.page_number,
            chunk_index=source.chunk_index,
            score=source.score,
            original_token_count=len(source.content.split()),
            context_token_count=len(source.content.split()),
        )
        for source in sources
    ]
    return RefragContextPackage(
        query=query,
        full_text_chunks=chunks,
        compressed_chunks=[],
        discarded_chunks=[],
        total_original_tokens=sum(chunk.original_token_count for chunk in chunks),
        total_context_tokens=sum(chunk.context_token_count for chunk in chunks),
        compression_strategy="document_fallback_v1",
    )


def trim_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit])
