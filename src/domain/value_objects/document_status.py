import enum


class DocumentStatus(enum.StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"