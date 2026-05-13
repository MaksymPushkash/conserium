from dataclasses import dataclass
from datetime import datetime
from typing import final
from uuid import UUID


@final
@dataclass(frozen=True, slots=True)
class NoteVersionDTO:
    id: UUID
    note_id: UUID
    version_number: int
    title: str
    content: str
    created_at: datetime
