from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None
 
 
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
 
 
class RefreshRequest(BaseModel):
    refresh_token: str
 
 
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"