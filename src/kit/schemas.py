from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class IdentifierSchema(Schema):
    id: UUID


class TimestampedSchema(Schema):
    created_at: datetime
    updated_at: datetime | None = None


__all__ = ["IdentifierSchema", "Schema", "TimestampedSchema"]
