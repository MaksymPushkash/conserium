from src.domain.entities.user_entity import UserEntity
from src.presentation.schemas.user import UserResponse


def to_user_response(user: UserEntity) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=str(user.email),
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
