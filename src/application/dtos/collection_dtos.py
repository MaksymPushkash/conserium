from dataclasses import dataclass
from datetime import datetime
from typing import final
from uuid import UUID


@final
@dataclass(frozen=True, slots=True)
class CreateCollectionDTO:
    user_id: UUID
    name: str
    description: str | None = None
    color: str | None = None


@final
@dataclass(frozen=True, slots=True)
class UpdateCollectionDTO:
    user_id: UUID
    collection_id: UUID
    name: str
    description: str | None = None
    color: str | None = None


@final
@dataclass(frozen=True, slots=True)
class DeleteCollectionDTO:
    user_id: UUID
    collection_id: UUID


@final
@dataclass(frozen=True, slots=True)
class ListCollectionsDTO:
    user_id: UUID
    limit: int = 100
    offset: int = 0


@final
@dataclass(frozen=True, slots=True)
class CollectionDTO:
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    color: str | None
    created_at: datetime
    updated_at: datetime | None


@final
@dataclass(frozen=True, slots=True)
class CollectionListDTO:
    items: list[CollectionDTO]
    total: int
    limit: int
    offset: int
