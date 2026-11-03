import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from meridian_ams.users.utils.enums import AccountType, UserRole, UserStatus
from meridian_ams.users.utils.validators import (
    validate_date_of_birth,
    validate_email,
    validate_name,
    validate_phone_number,
    validate_username,
    validate_work_email_domain_non_staff,
    validate_work_email_domain_staff,
)
from meridian_ams.utils.base_schema import BaseSchema


class UserResponseBaseAdmin(BaseModel):
    public_id: uuid.UUID

    first_name: str
    last_name: str
    middle_name: str | None

    role: UserRole

    model_config = ConfigDict(extra="ignore")


class UserResponseDetailedAdmin(UserResponseBaseAdmin, BaseSchema):
    date_of_birth: date | None
    address: str | None

    username: str
    email: str

    account_type: AccountType
    status: UserStatus

    created_at: datetime
    updated_at: datetime


class CreateUserBase(BaseModel):
    first_name: str = Field(min_length=3, max_length=30)
    last_name: str = Field(min_length=3, max_length=30)
    middle_name: str | None = Field(min_length=3, max_length=30, default=None)

    phone_number: str

    username: str = Field(min_length=6, max_length=20)
    email: str = Field(max_length=50)

    @field_validator("first_name")
    @classmethod
    def _validate_first_name(cls, v: str) -> str:
        return validate_name(value=v, field="first_name")

    @field_validator("last_name")
    @classmethod
    def _validate_last_name(cls, v: str) -> str:
        return validate_name(value=v, field="last_name")

    @field_validator("middle_name")
    @classmethod
    def _validate_middle_name(cls, v: str | None) -> str | None:
        if v is None:
            return None

        return validate_name(value=v, field="middle_name")

    @field_validator("phone_number")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        return validate_phone_number(v)

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        return validate_username(v)

    @field_validator("email", mode="after")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        return validate_email(v)


class CreateStudent(CreateUserBase):
    type: Literal["student"]

    date_of_birth: date
    address: str = Field(min_length=15, max_length=100)

    @field_validator("date_of_birth")
    @classmethod
    def _validate_date_of_birth(cls, v: date) -> date:
        return validate_date_of_birth(v)

    @model_validator(mode="after")
    def _validate_work_email_domain(self) -> "CreateStudent":
        validate_work_email_domain_non_staff(self.email)

        return self


class CreateStaff(CreateUserBase):
    type: Literal["staff"]

    date_of_birth: date | None = None
    address: str | None = Field(min_length=15, max_length=150, default=None)

    role: Literal[UserRole.DIRECTOR, UserRole.TEACHER]

    @field_validator("date_of_birth")
    @classmethod
    def _validate_date_of_birth(cls, v: date | None) -> date | None:
        if v is None:
            return None

        return validate_date_of_birth(v)

    @model_validator(mode="after")
    def _validate_work_email_domain(self) -> "CreateStaff":
        validate_work_email_domain_staff(self.email)

        return self


class CreateNewGuardian(CreateUserBase):
    type: Literal["new_guardian"]

    date_of_birth: date | None = None
    address: str | None = Field(min_length=15, max_length=150, default=None)

    @field_validator("date_of_birth")
    @classmethod
    def _validate_date_of_birth(cls, v: date | None) -> date | None:
        if v is None:
            return None

        return validate_date_of_birth(v)

    @model_validator(mode="after")
    def _validate_work_email_domain(self) -> "CreateNewGuardian":
        validate_work_email_domain_non_staff(self.email)

        return self


class CreateGuardianFromExistingIdentity(BaseModel):
    type: Literal["existing_identity"]

    public_id: uuid.UUID

    username: str = Field(min_length=6, max_length=20)
    email: str = Field(max_length=50)

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        return validate_username(v)

    @field_validator("email", mode="after")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        return validate_email(v)

    @model_validator(mode="after")
    def _validate_work_email_domain(self) -> "CreateGuardianFromExistingIdentity":
        validate_work_email_domain_non_staff(self.email)

        return self


CreateUserRequest = Annotated[
    CreateStudent
    | CreateStaff
    | CreateNewGuardian
    | CreateGuardianFromExistingIdentity,
    Field(discriminator="type"),
]
