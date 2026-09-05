import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.users.utils import validators
from src.utils.base_schema import BaseSchema


class UserResponseSelf(BaseSchema):
    public_id: uuid.UUID

    username: str

    firstname: str
    lastname: str
    middlename: str | None

    phone_number: str
    email: str

    date_of_birth: date | None
    address: str | None

    created_at: datetime


class UpdateUserCredentials(BaseModel):
    username: str | None = Field(min_length=6, max_length=20, default=None)
    email: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str | None) -> str | None:
        if v is None:
            return None

        return validators.validate_username(v)

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, v: EmailStr | None) -> str | None:
        if v is None:
            return None

        return validators.validate_email(v)
