import uuid

from src.application.dtos.query_dtos import QuerySourceDTO
from src.application.dtos.refrag_dtos import RefragRepresentation
from src.application.services.refrag.heuristic_context_builder import HeuristicRefragContextBuilder


def _source(index: int, *, score: float | None, content: str | None = None) -> QuerySourceDTO:
    return QuerySourceDTO(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=f"Document {index}",
        content=content or f"Sentence one for chunk {index}. Sentence two for chunk {index}. Sentence three for chunk {index}.",
        page_number=index,
        chunk_index=index,
        score=score,
    )


def test_refrag_builder_splits_full_compressed_and_discarded_chunks() -> None:
    builder = HeuristicRefragContextBuilder()
    sources = [
        _source(1, score=0.01),
        _source(2, score=0.01),
        _source(3, score=0.01),
        _source(4, score=0.02),
        _source(5, score=0.001),
    ]

    package = builder.build_context(query="architecture", sources=sources)

    assert [chunk.representation for chunk in package.full_text_chunks] == [
        RefragRepresentation.FULL_TEXT,
        RefragRepresentation.FULL_TEXT,
        RefragRepresentation.FULL_TEXT,
    ]
    assert package.compressed_chunks[0].chunk_id == sources[3].chunk_id
    assert package.compressed_chunks[0].representation == RefragRepresentation.COMPRESSED
    assert package.discarded_chunks[0].chunk_id == sources[4].chunk_id
    assert package.discarded_chunks[0].context_text == ""
    assert package.total_context_tokens < package.total_original_tokens


def test_refrag_builder_compresses_to_bounded_sentence_summary() -> None:
    builder = HeuristicRefragContextBuilder()
    source = _source(
        4,
        score=0.02,
        content="First important sentence. Second useful sentence. Third lower priority sentence.",
    )

    package = builder.build_context(query="architecture", sources=[_source(1, score=0.1), _source(2, score=0.1), _source(3, score=0.1), source])

    compressed = package.compressed_chunks[0]
    assert compressed.context_text == "First important sentence. Second useful sentence."
    assert compressed.chunk_id == source.chunk_id
    assert compressed.document_id == source.document_id
    assert compressed.page_number == source.page_number
