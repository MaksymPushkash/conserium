from datetime import UTC, datetime
from math import isfinite
from uuid import UUID


class ChunkEntity:
    EMBEDDING_DIMENSIONS = 1536

    def __init__(
        self,
        *,
        id: UUID,
        document_id: UUID,
        content: str,
        embedding: list[float],
        chunk_index: int,
        start_char: int | None,
        end_char: int | None,
        page_number: int | None,
        token_count: int | None,
        created_at: datetime,
    ) -> None:
        self._id = id
        self._document_id = document_id
        self._content = self._validate_content(content)
        self._embedding = self._validate_embedding(embedding)
        self._chunk_index = self._validate_non_negative_int(chunk_index, "chunk_index")
        self._start_char = self._validate_non_negative_optional_int(start_char, "start_char")
        self._end_char = self._validate_non_negative_optional_int(end_char, "end_char")
        self._page_number = self._validate_non_negative_optional_int(page_number, "page_number")
        self._token_count = self._validate_non_negative_optional_int(token_count, "token_count")
        self._created_at = self._validate_timestamp(created_at, "created_at")
        self._validate_char_range()

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def document_id(self) -> UUID:
        return self._document_id

    @property
    def content(self) -> str:
        return self._content

    @property
    def embedding(self) -> list[float]:
        return self._embedding.copy()

    @property
    def chunk_index(self) -> int:
        return self._chunk_index

    @property
    def start_char(self) -> int | None:
        return self._start_char

    @property
    def end_char(self) -> int | None:
        return self._end_char

    @property
    def page_number(self) -> int | None:
        return self._page_number

    @property
    def token_count(self) -> int | None:
        return self._token_count

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        document_id: UUID,
        content: str,
        embedding: list[float],
        chunk_index: int,
        start_char: int | None = None,
        end_char: int | None = None,
        page_number: int | None = None,
        token_count: int | None = None,
    ) -> "ChunkEntity":
        return cls(
            id=id,
            document_id=document_id,
            content=content,
            embedding=embedding,
            chunk_index=chunk_index,
            start_char=start_char,
            end_char=end_char,
            page_number=page_number,
            token_count=token_count,
            created_at=datetime.now(UTC),
        )

    def update_embedding(self, embedding: list[float]) -> None:
        self._embedding = self._validate_embedding(embedding)

    @staticmethod
    def _validate_content(content: str) -> str:
        if not content.strip():
            raise ValueError("content cannot be empty")
        return content

    @staticmethod
    def _validate_non_negative_int(value: int, field_name: str) -> int:
        if value < 0:
            raise ValueError(f"{field_name} cannot be negative")
        return value

    @classmethod
    def _validate_non_negative_optional_int(cls, value: int | None, field_name: str) -> int | None:
        if value is None:
            return None
        return cls._validate_non_negative_int(value, field_name)

    @classmethod
    def _validate_embedding(cls, embedding: list[float]) -> list[float]:
        if len(embedding) != cls.EMBEDDING_DIMENSIONS:
            raise ValueError(f"embedding must have {cls.EMBEDDING_DIMENSIONS} dimensions")
        if not all(isfinite(float(value)) for value in embedding):
            raise ValueError("embedding must contain only finite numeric values")
        return [float(value) for value in embedding]

    @staticmethod
    def _validate_timestamp(value: datetime, field_name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value

    def _validate_char_range(self) -> None:
        if self._start_char is not None and self._end_char is not None and self._end_char < self._start_char:
            raise ValueError("end_char cannot be smaller than start_char")

    def __repr__(self) -> str:
        return f"ChunkEntity(id={self._id}, document_id={self._document_id}, chunk_index={self._chunk_index})"
