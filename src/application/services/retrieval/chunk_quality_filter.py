from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.dtos.query_dtos import QuerySourceDTO

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_MIN_ALNUM_CHARS = 24
_MIN_WORDS = 4
_MIN_UNIQUE_WORDS = 3
_GARBAGE_PHRASES = {
    "hello",
    "hello text",
    "test",
    "test text",
    "sample",
    "sample text",
    "lorem ipsum",
}
_GARBAGE_SUBSTRINGS = {
    "intentionally irrelevant",
    "intentionally unrelated",
    "should not be selected",
    "synthetic noise",
    "unrelated synthetic noise",
}
_STOP_WORDS = {
    "a",
    "about",
    "after",
    "all",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "collection",
    "current",
    "does",
    "document",
    "documented",
    "for",
    "from",
    "give",
    "how",
    "in",
    "inside",
    "is",
    "it",
    "live",
    "me",
    "my",
    "of",
    "on",
    "or",
    "recommend",
    "recommended",
    "say",
    "should",
    "summarize",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "with",
}


class ChunkQualityFilter:
    def filter_sources(self, sources: list[QuerySourceDTO]) -> list[QuerySourceDTO]:
        return [source for source in sources if is_quality_chunk(source.content)]


class ChunkRelevanceFilter:
    def filter_sources(self, query: str, sources: list[QuerySourceDTO]) -> list[QuerySourceDTO]:
        query_terms = _meaningful_terms(query)
        if not query_terms:
            return sources
        required_overlap = _required_query_overlap(len(query_terms))
        return [
            source
            for source in sources
            if _source_query_overlap(query_terms, source) >= required_overlap
        ]


def is_quality_chunk(content: str) -> bool:
    normalized = " ".join(content.casefold().split())
    if not normalized:
        return False
    if normalized in _GARBAGE_PHRASES:
        return False
    if any(phrase in normalized for phrase in _GARBAGE_SUBSTRINGS):
        return False
    words = _WORD_RE.findall(normalized)
    if len(words) < _MIN_WORDS:
        return False
    if len(set(words)) < _MIN_UNIQUE_WORDS:
        return False
    alnum_chars = sum(1 for character in normalized if character.isalnum())
    return alnum_chars >= _MIN_ALNUM_CHARS


def _meaningful_terms(text: str) -> set[str]:
    return {
        normalized
        for word in _WORD_RE.findall(text.casefold())
        if len(word) > 2 and (normalized := _normalize_term(word)) not in _STOP_WORDS
    }


def _source_query_overlap(query_terms: set[str], source: QuerySourceDTO) -> int:
    title = source.document_title or ""
    content_terms = _meaningful_terms(f"{title} {source.content}")
    return len(query_terms & content_terms)


def _required_query_overlap(query_term_count: int) -> int:
    if query_term_count <= 3:
        return query_term_count
    if query_term_count <= 5:
        return query_term_count - 1
    return max(3, (query_term_count * 3 + 4) // 5)


def _normalize_term(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return f"{word[:-3]}y"
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word
