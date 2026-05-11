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


class ChunkQualityFilter:
    def filter_sources(self, sources: list[QuerySourceDTO]) -> list[QuerySourceDTO]:
        return [source for source in sources if is_quality_chunk(source.content)]


def is_quality_chunk(content: str) -> bool:
    normalized = " ".join(content.casefold().split())
    if not normalized:
        return False
    if normalized in _GARBAGE_PHRASES:
        return False
    words = _WORD_RE.findall(normalized)
    if len(words) < _MIN_WORDS:
        return False
    if len(set(words)) < _MIN_UNIQUE_WORDS:
        return False
    alnum_chars = sum(1 for character in normalized if character.isalnum())
    return alnum_chars >= _MIN_ALNUM_CHARS
