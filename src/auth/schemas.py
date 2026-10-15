from pydantic import BaseModel, field_validator, model_validator

from src.users.utils.validators import validate_password


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


class PasswordResetRequestPublic(BaseModel):
    email: str


class ResetPassword(BaseModel):
    reset_password_token: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def _validate_password_strength(cls, v: str) -> str:
        return validate_password(v)

    @model_validator(mode="after")
    def _validate_passwords_match(self) -> "ResetPassword":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self
