from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.domain.entities.user_entity import UserEntity


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None
 
    @classmethod
    def from_entity(cls, user: UserEntity) -> "UserResponse":
        return cls(
            id=user.id,
            email=str(user.email),
            display_name=user.display_name,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )