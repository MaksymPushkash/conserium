import uuid

from src.application.dtos.auth_dtos import RegisterDTO, TokenResponseDTO
from src.application.interfaces.cache import ICache
from src.application.interfaces.jwt_service import IJWTService
from src.application.interfaces.password_hasher import IPasswordHasher
from src.application.interfaces.unit_of_work import IUnitOfWork
from src.application.use_cases.auth.base import BaseAuthUseCase
from src.domain.entities.user_entity import UserEntity
from src.domain.exceptions import EmailAlreadyExistsException
from src.domain.value_objects.email import Email


class RegisterUserUseCase(BaseAuthUseCase):
    def __init__(
        self,
        uow: IUnitOfWork,
        password_hasher: IPasswordHasher,
        jwt_service: IJWTService,
        cache: ICache,
        refresh_token_ttl_seconds: int,
    ) -> None:
        super().__init__(jwt_service, cache, refresh_token_ttl_seconds)
        self._uow = uow
        self._password_hasher = password_hasher
 
    async def __call__(self, dto: RegisterDTO) -> TokenResponseDTO:
        async with self._uow:
            already_exists = await self._uow.user_repo.exists_by_email(dto.email)
            if already_exists:
                raise EmailAlreadyExistsException(f"{dto.email} already registered")
 
            user = UserEntity.create(
                id=uuid.uuid4(),
                email=Email(value=dto.email),
                password=self._password_hasher.hash(dto.password),
                display_name=dto.display_name,
            )
 
            await self._uow.user_repo.create(user)
            await self._uow.commit()
 
        return await self._issue_tokens(user.id)