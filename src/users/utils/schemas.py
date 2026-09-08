from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.users.utils import validators
from src.users.utils.enums import UserRole


@dataclass
class LoadOptionsSchema:
    load_identity: bool = False
    load_sessions: bool = False
    load_activation: bool = False
    load_login_lockout: bool = False
    load_email_change: bool = False
    load_password_reset: bool = False


class UserResponseBase(BaseModel):
    firstname: str
    lastname: str
    middlename: str | None

    phone_number: str

    role: UserRole

    model_config = ConfigDict(extra="ignore")


class UpdateCredentials(BaseModel):
    username: str | None = Field(min_length=6, max_length=20, default=None)
    email: str | None = None

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str | None) -> str | None:
        if v is None:
            return None

        return validators.validate_username(v)

    @field_validator("email", mode="after")
    @classmethod
    def _validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None

        return validators.validate_email(v)

    @model_validator(mode="after")
    def _validate_at_least_one_field(self) -> "UpdateCredentials":
        if self.username is None and self.email is None:
            raise ValueError("At least one of username or email must be provided.")

        return self
