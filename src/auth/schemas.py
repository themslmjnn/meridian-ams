import uuid
from dataclasses import dataclass

from pydantic import BaseModel, EmailStr, field_validator, model_validator

from src.users.utils.enums import AccountType, UserRole
from src.users.utils.validators import validate_password


@dataclass
class CreateAccessToken:
    public_id: uuid.UUID
    role: UserRole
    account_type: AccountType
    session_id: int
    access_token_version: int


@dataclass
class CreateRefreshToken:
    public_id: uuid.UUID
    session_id: int


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ActivateAccount(BaseModel):
    activation_token: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def _validate_password_strength(cls, v: str) -> str:
        return validate_password(v)

    @model_validator(mode="after")
    def _validate_passwords_match(self) -> "ActivateAccount":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")

        return self


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

    @model_validator(mode="after")
    def _validate_passwords_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self
