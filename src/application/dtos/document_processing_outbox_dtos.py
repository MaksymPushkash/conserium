from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DocumentProcessingOutboxDTO:
    id: UUID
    document_id: UUID
    task_name: str
    status: str
    attempts: int
    locked_at: datetime | None
    last_error: str | None
    dispatched_at: datetime | None
    created_at: datetime
    updated_at: datetime | None
