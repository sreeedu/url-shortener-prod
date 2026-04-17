from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from app.core.security import validate_password_strength


class SignupRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        valid, msg = validate_password_strength(v)
        if not valid:
            raise ValueError(msg)
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    # Cap matches SignupRequest — prevents CPU DoS via oversized SHA-256 input
    # even though bcrypt truncation is already avoided by pre-hashing.
    password: str = Field(..., max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    # 2048 matches the middleware token-length guard — reject oversized tokens
    # at schema validation before they reach any crypto code.
    refresh_token: str = Field(..., max_length=2048)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        valid, msg = validate_password_strength(v)
        if not valid:
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def passwords_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr



class UserResponse(BaseModel):
    id: str
    email: str
    is_verified: bool
    is_platform_admin: bool
    created_at: str

    class Config:
        from_attributes = True
