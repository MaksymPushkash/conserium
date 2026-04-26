from src.application.dtos.auth_dtos import LoginDTO, TokenResponseDTO
from src.application.interfaces.cache import ICache
from src.application.interfaces.jwt_service import IJWTService
from src.application.interfaces.password_hasher import IPasswordHasher
from src.application.interfaces.unit_of_work import IUnitOfWork
from src.application.use_cases.auth.base import BaseAuthUseCase
from src.domain.exceptions import InvalidCredentialsException


class LoginUserUseCase(BaseAuthUseCase):
    def __init__(
        self,
        uow: IUnitOfWork,
        password_hasher: IPasswordHasher,
        jwt_service: IJWTService,
        cache: ICache,
    ) -> None:
        self._uow = uow
        self._password_hasher = password_hasher
        self._jwt_service = jwt_service
        self._cache = cache
 
    async def __call__(self, dto: LoginDTO) -> TokenResponseDTO:
        async with self._uow:
            user = await self._uow.user_repo.get_by_email(dto.email)
 
            if user is None:
                raise InvalidCredentialsException("invalid email or password")
 
            if not self._password_hasher.verify(dto.password, str(user.password)):
                raise InvalidCredentialsException("invalid email or password")
 
            user.ensure_active()
 
        return await self._issue_tokens(user.id)