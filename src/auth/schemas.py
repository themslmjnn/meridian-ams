import uuid

from pydantic import BaseModel, EmailStr, field_validator

from src.users.utils.enums import AccountType, UserRole
from src.users.utils.validators import validate_password


class CreateAccessToken(BaseModel):
    public_id: uuid.UUID
    role: UserRole
    account_type: AccountType
    session_id: int
    access_token_version: int


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CreateRefreshToken:
    public_id: uuid.UUID
    session_id: int


class ActivateAccount(BaseModel):
    activation_token: str
    password: str
    confirm_password: str

    @field_validator("password")
    @classmethod
    def _validate_password_strength(cls, v: str) -> str:
        return validate_password(v)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    reset_password_token: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def _validate_password_strength(cls, v: str) -> str:
        return validate_password(v)
