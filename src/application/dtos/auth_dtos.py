from dataclasses import dataclass
from typing import final


@final
@dataclass(frozen=True, slots=True)
class RegisterDTO:
    email: str
    password: str
    display_name: str | None = None


@final
@dataclass(frozen=True, slots=True)
class LoginDTO:
    email: str
    password: str


@final
@dataclass(frozen=True, slots=True)
class RefreshDTO:
    refresh_token: str


@final
@dataclass(frozen=True, slots=True)
class OAuthProfileDTO:
    email: str
    display_name: str | None = None


@final
@dataclass(frozen=True, slots=True)
class CompleteOAuthLoginDTO:
    code: str
    redirect_uri: str


@final
@dataclass(frozen=True, slots=True)
class TokenResponseDTO:
    access_token: str
    refresh_token: str
