from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.interfaces.user_repository import IUserRepository
from src.domain.entities.user_entity import UserEntity
from src.domain.value_objects.email import Email
from src.infrastructure.database.models.user import UserModel


class SQLAlchemyUserRepository(IUserRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session


    async def get_by_id(self, user_id: UUID) -> UserEntity | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_email(self, email: str) -> UserEntity | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def exists_by_email(self, email: str) -> bool:
        result = await self._session.execute(
            select(exists().where(UserModel.email == email))
        )
        return result.scalar_one()


    async def create(self, user: UserEntity) -> None:
        model = self._to_model(user)
        self._session.add(model)

    async def update(self, user: UserEntity) -> None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.id == user.id)
        )
        model = result.scalar_one()
        model.email = str(user.email)
        model.hashed_password = str(user.password)
        model.display_name = user.display_name
        model.is_active = user.is_active
        model.updated_at = user.updated_at



    def _to_entity(self, model: UserModel) -> UserEntity:
        return UserEntity(
            id=model.id,
            email=Email(value=model.email),
            password=model.hashed_password,
            display_name=model.display_name,
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: UserEntity) -> UserModel:
        return UserModel(
            id=entity.id,
            email=str(entity.email),
            hashed_password=str(entity.password),
            display_name=entity.display_name,
            is_active=entity.is_active,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
