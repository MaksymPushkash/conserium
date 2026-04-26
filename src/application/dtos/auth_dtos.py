from dataclasses import dataclass
from typing import final


@final
@dataclass(frozen=True)
class RegisterDTO:
    email: str
    password: str
    display_name: str | None = None
 
 
@final
@dataclass(frozen=True)
class LoginDTO:
    email: str
    password: str
 
 
@final
@dataclass(frozen=True)
class RefreshDTO:
    refresh_token: str
 
 
@final
@dataclass(frozen=True)
class TokenResponseDTO:
    access_token: str
    refresh_token: str