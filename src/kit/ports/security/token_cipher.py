from abc import ABC, abstractmethod


class ITokenCipher(ABC):
    @abstractmethod
    def encrypt(self, value: str) -> str: ...

    @abstractmethod
    def decrypt(self, value: str) -> str: ...
