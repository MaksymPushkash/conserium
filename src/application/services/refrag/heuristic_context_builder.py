from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.application.dtos.refrag_dtos import RefragChunk, RefragContextPackage, RefragRepresentation
from src.application.ports.refrag.refrag_context_builder import IRefragContextBuilder

if TYPE_CHECKING:
    from src.application.dtos.query_dtos import QuerySourceDTO

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class HeuristicRefragContextBuilder(IRefragContextBuilder):
    FULL_TEXT_TOP_K = 3
    FULL_TEXT_SCORE_THRESHOLD = 0.035
    COMPRESSED_SCORE_THRESHOLD = 0.015
    COMPRESSED_SENTENCE_LIMIT = 2
    COMPRESSED_TOKEN_LIMIT = 80
    STRATEGY_NAME = "heuristic_v1_top3_score_threshold_sentence_compression"

    def build_context(self, *, query: str, sources: list[QuerySourceDTO]) -> RefragContextPackage:
        full_text_chunks: list[RefragChunk] = []
        compressed_chunks: list[RefragChunk] = []
        discarded_chunks: list[RefragChunk] = []

        for rank, source in enumerate(sources, start=1):
            representation = self._choose_representation(source, rank)
            context_text = (
                source.content
                if representation == RefragRepresentation.FULL_TEXT
                else self._compress_text(source.content)
            )
            refrag_chunk = self._to_refrag_chunk(source, representation, context_text)
            if representation == RefragRepresentation.FULL_TEXT:
                full_text_chunks.append(refrag_chunk)
            elif representation == RefragRepresentation.COMPRESSED:
                compressed_chunks.append(refrag_chunk)
            else:
                discarded_chunks.append(refrag_chunk)

        return RefragContextPackage(
            query=query,
            full_text_chunks=full_text_chunks,
            compressed_chunks=compressed_chunks,
            discarded_chunks=discarded_chunks,
            total_original_tokens=sum(_estimate_tokens(source.content) for source in sources),
            total_context_tokens=sum(
                chunk.context_token_count for chunk in [*full_text_chunks, *compressed_chunks]
            ),
            compression_strategy=self.STRATEGY_NAME,
        )

    def _choose_representation(self, source: QuerySourceDTO, rank: int) -> RefragRepresentation:
        score = source.score
        if rank <= self.FULL_TEXT_TOP_K or (score is not None and score >= self.FULL_TEXT_SCORE_THRESHOLD):
            return RefragRepresentation.FULL_TEXT
        if score is None or score >= self.COMPRESSED_SCORE_THRESHOLD:
            return RefragRepresentation.COMPRESSED
        return RefragRepresentation.DISCARDED

    def _compress_text(self, text: str) -> str:
        sentences = [sentence.strip() for sentence in _SENTENCE_SPLIT_RE.split(text.strip()) if sentence.strip()]
        summary = " ".join(sentences[: self.COMPRESSED_SENTENCE_LIMIT]) if sentences else text.strip()
        words = summary.split()
        if len(words) <= self.COMPRESSED_TOKEN_LIMIT:
            return summary
        return " ".join(words[: self.COMPRESSED_TOKEN_LIMIT])

    @staticmethod
    def _to_refrag_chunk(
        source: QuerySourceDTO,
        representation: RefragRepresentation,
        context_text: str,
    ) -> RefragChunk:
        return RefragChunk(
            chunk_id=source.chunk_id,
            document_id=source.document_id,
            document_title=source.document_title,
            original_text=source.content,
            context_text="" if representation == RefragRepresentation.DISCARDED else context_text,
            representation=representation,
            page_number=source.page_number,
            chunk_index=source.chunk_index,
            score=source.score,
            original_token_count=_estimate_tokens(source.content),
            context_token_count=0 if representation == RefragRepresentation.DISCARDED else _estimate_tokens(context_text),
        )


def _estimate_tokens(text: str) -> int:
    return len(text.split())
