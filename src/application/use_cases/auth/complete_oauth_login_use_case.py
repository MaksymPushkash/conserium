import uuid

from src.application.dtos.auth_dtos import CompleteOAuthLoginDTO, TokenResponseDTO
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.auth.oauth_provider import IOAuthProviderClient
from src.application.ports.auth.password_hasher import IPasswordHasher
from src.application.ports.cache.cache import ICache
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.auth.base import BaseAuthUseCase
from src.domain.entities.user_entity import UserEntity
from src.domain.value_objects.email import Email


class CompleteOAuthLoginUseCase(BaseAuthUseCase):
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

    async def __call__(self, dto: CompleteOAuthLoginDTO, provider: IOAuthProviderClient) -> TokenResponseDTO:
        profile = await provider.fetch_user_profile(code=dto.code, redirect_uri=dto.redirect_uri)

        async with self._uow:
            user = await self._uow.user_repo.get_by_email(profile.email)
            if user is None:
                user = UserEntity.create(
                    id=uuid.uuid4(),
                    email=Email(value=profile.email),
                    password=self._password_hasher.hash(uuid.uuid4().hex),
                    display_name=profile.display_name,
                )
                await self._uow.user_repo.create(user)
                await self._uow.commit()
            else:
                user.ensure_active()

        return await self._issue_tokens(user.id)
