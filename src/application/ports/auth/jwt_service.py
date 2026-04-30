from abc import ABC, abstractmethod
from uuid import UUID


class IJWTService(ABC):
    @abstractmethod
    def generate_access_token(self, user_id: UUID) -> str: ...

    @abstractmethod
    def generate_refresh_token(self, user_id: UUID) -> str: ...

    @abstractmethod
    def verify_access_token(self, token: str) -> UUID: ...

    @abstractmethod
    def verify_refresh_token(self, token: str) -> UUID: ...
