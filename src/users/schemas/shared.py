import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

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


class ConfirmEmailChange(BaseModel):
    code: str


class UpdateMePassword(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=100)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        return validators.validate_password(v)

    @model_validator(mode="after")
    def _validate_passwords_differ(self) -> "UpdateMePassword":
        if self.current_password == self.new_password:
            raise ValueError("New password must differ from current password")

        return self
