from __future__ import annotations

from dataclasses import dataclass

from src.documents.schemas import TextChunk


@dataclass(frozen=True, slots=True)
class _TextSpan:
    start_char: int
    end_char: int


class SimpleTextChunker:
    DEFAULT_MAX_CHUNK_CHARS = 1400

    def __init__(self, max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS) -> None:
        if max_chunk_chars <= 0:
            raise ValueError("max_chunk_chars must be positive")
        self._max_chunk_chars = max_chunk_chars

    def chunk_text(self, text: str) -> list[TextChunk]:
        if not text.strip():
            return []

        chunks: list[TextChunk] = []
        current_start: int | None = None
        current_end: int | None = None

        for span in self._paragraph_spans(text):
            if span.end_char - span.start_char > self._max_chunk_chars:
                if current_start is not None and current_end is not None:
                    chunks.append(self._build_chunk(text, current_start, current_end, len(chunks)))
                    current_start = None
                    current_end = None
                for split_span in self._split_long_span(text, span):
                    chunks.append(self._build_chunk(text, split_span.start_char, split_span.end_char, len(chunks)))
                continue

            if current_start is None:
                current_start = span.start_char
                current_end = span.end_char
                continue

            if current_end is not None and span.end_char - current_start <= self._max_chunk_chars:
                current_end = span.end_char
                continue

            if current_end is not None:
                chunks.append(self._build_chunk(text, current_start, current_end, len(chunks)))
            current_start = span.start_char
            current_end = span.end_char

        if current_start is not None and current_end is not None:
            chunks.append(self._build_chunk(text, current_start, current_end, len(chunks)))

        return chunks

    @staticmethod
    def _paragraph_spans(text: str) -> list[_TextSpan]:
        spans: list[_TextSpan] = []
        paragraph_start: int | None = None
        paragraph_end: int | None = None
        cursor = 0

        for line in text.splitlines(keepends=True):
            line_start = cursor
            line_end = cursor + len(line)
            cursor = line_end

            content_without_newline = line.rstrip("\r\n")
            if not content_without_newline.strip():
                if paragraph_start is not None and paragraph_end is not None:
                    spans.append(_TextSpan(start_char=paragraph_start, end_char=paragraph_end))
                    paragraph_start = None
                    paragraph_end = None
                continue

            leading_chars = len(content_without_newline) - len(content_without_newline.lstrip())
            trimmed_end = line_start + len(content_without_newline.rstrip())
            if paragraph_start is None:
                paragraph_start = line_start + leading_chars
            paragraph_end = trimmed_end

        if paragraph_start is not None and paragraph_end is not None:
            spans.append(_TextSpan(start_char=paragraph_start, end_char=paragraph_end))

        return spans

    def _split_long_span(self, text: str, span: _TextSpan) -> list[_TextSpan]:
        spans: list[_TextSpan] = []
        cursor = span.start_char

        while cursor < span.end_char:
            while cursor < span.end_char and text[cursor].isspace():
                cursor += 1
            if cursor >= span.end_char:
                break

            proposed_end = min(cursor + self._max_chunk_chars, span.end_char)
            split_end = proposed_end
            if proposed_end < span.end_char:
                whitespace_index = text.rfind(" ", cursor, proposed_end + 1)
                newline_index = text.rfind("\n", cursor, proposed_end + 1)
                split_index = max(whitespace_index, newline_index)
                if split_index > cursor:
                    split_end = split_index

            while split_end > cursor and text[split_end - 1].isspace():
                split_end -= 1

            if split_end == cursor:
                split_end = min(cursor + self._max_chunk_chars, span.end_char)

            spans.append(_TextSpan(start_char=cursor, end_char=split_end))
            cursor = split_end

        return spans

    @staticmethod
    def _build_chunk(text: str, start_char: int, end_char: int, chunk_index: int) -> TextChunk:
        content = text[start_char:end_char]
        return TextChunk(
            content=content,
            chunk_index=chunk_index,
            start_char=start_char,
            end_char=end_char,
            token_count=len(content.split()),
        )
