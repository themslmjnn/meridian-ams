import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from meridian_ams.users.utils.enums import AccountType, UserRole, UserStatus
from meridian_ams.users.utils.validators import (
    validate_date_of_birth_non_student,
    validate_date_of_birth_student,
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


class CredentialsFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    username: str = Field(min_length=6, max_length=20)
    email: str = Field(max_length=50)

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        return validate_username(v)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        return validate_email(v)


class CreateUserBase(CredentialsFields):
    first_name: str = Field(min_length=3, max_length=30)
    last_name: str = Field(min_length=3, max_length=30)
    middle_name: str | None = Field(min_length=3, max_length=30, default=None)

    phone_number: str

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


class CreateStudentAdmin(CreateUserBase):
    type: Literal["student"]

    date_of_birth: date
    address: str = Field(min_length=15, max_length=150)

    @field_validator("date_of_birth")
    @classmethod
    def _validate_date_of_birth(cls, v: date) -> date:
        return validate_date_of_birth_student(v)

    @model_validator(mode="after")
    def _validate_work_email_domain(self) -> "CreateStudentAdmin":
        validate_work_email_domain_non_staff(self.email)

        return self


class CreateStaffAdmin(CreateUserBase):
    type: Literal["staff"]

    date_of_birth: date | None = None
    address: str | None = Field(min_length=15, max_length=150, default=None)

    role: Literal[UserRole.DIRECTOR, UserRole.TEACHER]

    @field_validator("date_of_birth")
    @classmethod
    def _validate_date_of_birth(cls, v: date | None) -> date | None:
        if v is None:
            return None

        return validate_date_of_birth_non_student(v)

    @model_validator(mode="after")
    def _validate_work_email_domain(self) -> "CreateStaffAdmin":
        validate_work_email_domain_staff(self.email)

        return self


class CreateGuardianAdmin(CreateUserBase):
    type: Literal["guardian"]

    date_of_birth: date | None = None
    address: str | None = Field(min_length=15, max_length=150, default=None)

    @field_validator("date_of_birth")
    @classmethod
    def _validate_date_of_birth(cls, v: date | None) -> date | None:
        if v is None:
            return None

        return validate_date_of_birth_non_student(v)

    @model_validator(mode="after")
    def _validate_work_email_domain(self) -> "CreateGuardianAdmin":
        validate_work_email_domain_non_staff(self.email)

        return self


class CreateUserFromExistingIdentityAdmin(BaseModel):
    type: Literal["existing_identity"]

    existing_user_public_id: uuid.UUID

    role: Literal[UserRole.TEACHER, UserRole.DIRECTOR, UserRole.GUARDIAN]

    @model_validator(mode="after")
    def _validate_work_email_domain(self) -> "CreateUserFromExistingIdentityAdmin":
        if self.role in [UserRole.TEACHER, UserRole.DIRECTOR]:
            validate_work_email_domain_staff(self.email)
        elif self.role == UserRole.GUARDIAN:
            validate_work_email_domain_non_staff(self.email)

        return self


CreateUserRequest = Annotated[
    CreateStudentAdmin
    | CreateStaffAdmin
    | CreateGuardianAdmin
    | CreateUserFromExistingIdentityAdmin,
    Field(discriminator="type"),
]
