from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class NoteVersionRecord:
    id: UUID
    note_id: UUID
    user_id: UUID
    version_number: int
    title: str
    content: str
    created_at: datetime | None = None


class INoteVersionRepository(ABC):
    @abstractmethod
    async def create(self, version: NoteVersionRecord) -> None: ...

    @abstractmethod
    async def list_by_note_id(self, *, note_id: UUID, user_id: UUID) -> list[NoteVersionRecord]: ...

    @abstractmethod
    async def get_by_id(self, *, version_id: UUID, note_id: UUID, user_id: UUID) -> NoteVersionRecord | None: ...

    @abstractmethod
    async def count_by_note_id(self, note_id: UUID) -> int: ...
