import base64
import hashlib

from cryptography.fernet import Fernet

from src.kit.ports.security.token_cipher import ITokenCipher


class FernetTokenCipher(ITokenCipher):
    def __init__(self, secret: str, *, key_version: str = "v1") -> None:
        if not secret:
            raise ValueError("token encryption secret is required")
        self._key_version = key_version.strip()
        if not self._key_version:
            raise ValueError("token encryption key version is required")
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        encrypted = self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        return f"{self._key_version}:{encrypted}"

    def decrypt(self, value: str) -> str:
        key_version, encrypted = value.split(":", 1)
        if key_version != self._key_version:
            raise ValueError("unsupported token encryption key version")
        return self._fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
