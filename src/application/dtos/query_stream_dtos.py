from dataclasses import dataclass
from enum import StrEnum
from typing import Any, final
from uuid import UUID


class QueryStreamEventType(StrEnum):
    METADATA = "metadata"
    TOKEN = "token"
    SOURCES = "sources"
    REFRAG_CONTEXT = "refrag_context"
    DONE = "done"
    ERROR = "error"


@final
@dataclass(frozen=True, slots=True)
class QueryStreamEventDTO:
    event: QueryStreamEventType
    data: dict[str, Any]


@final
@dataclass(frozen=True, slots=True)
class QueryStreamMetadataDTO:
    query_id: UUID
    query: str
    source_count: int
