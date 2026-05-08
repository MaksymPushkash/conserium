from abc import ABC, abstractmethod

from src.application.dtos.auth_dtos import OAuthProfileDTO


class IOAuthProviderClient(ABC):
    @abstractmethod
    def authorization_url(self, *, redirect_uri: str, state: str) -> str: ...

    @abstractmethod
    async def fetch_user_profile(self, *, code: str, redirect_uri: str) -> OAuthProfileDTO: ...
