from src.application.dtos.auth_dtos import LoginDTO, TokenResponseDTO
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.auth.password_hasher import IPasswordHasher
from src.application.ports.cache.cache import ICache
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.auth.base import BaseAuthUseCase
from src.domain.exceptions import InvalidCredentialsException


class LoginUserUseCase(BaseAuthUseCase):
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
 
    async def __call__(self, dto: LoginDTO) -> TokenResponseDTO:
        async with self._uow:
            user = await self._uow.user_repo.get_by_email(dto.email)
 
            if user is None:
                raise InvalidCredentialsException("invalid email or password")
 
            if not self._password_hasher.verify(dto.password, str(user.password)):
                raise InvalidCredentialsException("invalid email or password")
 
            user.ensure_active()
 
        return await self._issue_tokens(user.id)