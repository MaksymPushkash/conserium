from dataclasses import dataclass
from typing import final
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


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


@final
@dataclass(frozen=True, slots=True)
class UpdateUserPreferencesDTO:
    user_id: UUID
    preferences: dict[str, object]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
