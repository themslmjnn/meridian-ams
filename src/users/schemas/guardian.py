from pydantic import BaseModel, Field, field_validator

from src.users.utils import validators


class UpdateProfileGuardian(BaseModel):
    firstname: str | None = Field(min_length=3, max_length=50, default=None)
    lastname: str | None = Field(min_length=3, max_length=50, default=None)
    middlename: str | None = Field(min_length=3, max_length=50, default=None)

    phone_number: str | None = None

    @field_validator("firstname")
    @classmethod
    def validate_firstname(cls, v: str | None) -> str | None:
        if v is None:
            return None

        return validators.validate_firstname(v)

    @field_validator("lastname")
    @classmethod
    def validate_lastname(cls, v: str | None) -> str | None:
        if v is None:
            return None

        return validators.validate_lastname(v)

    @field_validator("middlename")
    @classmethod
    def validate_middlename(cls, v: str | None) -> str | None:
        if v is None:
            return None

        return validators.validate_middlename(v)

    @field_validator("phone_number", mode="after")
    @classmethod
    def validate_phone_number(cls, field: str | None) -> str | None:
        if field is None:
            return None

        return validators.validate_phone_number(field)
