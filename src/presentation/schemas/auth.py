from pydantic import BaseModel, EmailStr, Field


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
    refresh_token: str
    token_type: str = "bearer"
