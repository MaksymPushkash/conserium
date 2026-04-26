import hashlib

import bcrypt

from src.application.interfaces.password_hasher import IPasswordHasher


class BcryptPasswordHasher(IPasswordHasher):

    def _prehash(self, password: str) -> bytes:
        return hashlib.sha256(password.encode()).digest()

    def hash(self, password: str) -> str:
        return bcrypt.hashpw(
            self._prehash(password), bcrypt.gensalt()
        ).decode()

    def verify(self, plain: str, hashed: str) -> bool:
        return bcrypt.checkpw(
            self._prehash(plain), hashed.encode()
        )