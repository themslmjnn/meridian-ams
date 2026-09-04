import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from src.users.utils import validators
from src.users.utils.enums import AccountType, UserRole, UserStatus
from src.utils.base_schema import BaseSchema


class UserResponseBase(BaseModel):
    firstname: str
    lastname: str
    middlename: str | None


class UserResponseAdminDetailed(UserResponseBase, BaseSchema):
    date_of_birth: date | None
    address: str | None

    public_id: uuid.UUID

    username: str
    phone_number: str
    email: str

    role: UserRole
    account_type: AccountType
    status: UserStatus

    deletion_scheduled_for: datetime | None
    created_at: datetime
    updated_at: datetime


class CreateUserBase(BaseModel):
    firstname: str = Field(min_length=3, max_length=50)
    lastname: str = Field(min_length=3, max_length=50)
    middlename: str | None = Field(min_length=3, max_length=50, default=None)

    username: str = Field(min_length=6, max_length=20)
    phone_number: str
    email: str

    @field_validator("firstname")
    @classmethod
    def _validate_firstname(cls, v: str) -> str:
        return validators.validate_firstname(v)

    @field_validator("lastname")
    @classmethod
    def _validate_lastname(cls, v: str) -> str:
        return validators.validate_lastname(v)

    @field_validator("middlename")
    @classmethod
    def _validate_middlename(cls, v: str | None) -> str | None:
        if v is None:
            return None

        return validators.validate_middlename(v)

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        return validators.validate_username(v)

    @field_validator("phone_number")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        return validators.validate_phone_number(v)

    @field_validator("email", mode="after")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        return validators.validate_email(v)


class CreateStudentAdmin(CreateUserBase):
    type: Literal["student"] = "student"

    date_of_birth: date
    address: str | None = Field(min_length=15, max_length=100, default=None)

    @field_validator("date_of_birth")
    @classmethod
    def _validate_date_of_birth(cls, v: date) -> date:
        return validators.validate_date_of_birth(v)


class CreateStaffAdmin(CreateUserBase):
    type: Literal["staff"] = "staff"

    role: Literal[UserRole.DIRECTOR, UserRole.TEACHER] = UserRole.TEACHER

    @model_validator(mode="after")
    def _validate_work_email_domain(self) -> "CreateStaffAdmin":
        validators.validate_work_email_domain(self.email)

        return self


class CreateGuardianAdmin(CreateUserBase):
    type: Literal["guardian"] = "guardian"

    existing_identity_id: int | None = None


CreateUserRequest = Annotated[
    CreateStudentAdmin | CreateStaffAdmin | CreateGuardianAdmin,
    Field(discriminator="type"),
]


class UpdateUserBase(BaseModel):
    firstname: str | None = Field(min_length=3, max_length=50, default=None)
    lastname: str | None = Field(min_length=3, max_length=50, default=None)
    middlename: str | None = Field(min_length=3, max_length=50, default=None)

    phone_number: str | None = None

    @field_validator("firstname")
    @classmethod
    def _validate_firstname(cls, v: str | None) -> str | None:
        if v is None:
            return None

        return validators.validate_firstname(v)

    @field_validator("lastname")
    @classmethod
    def _validate_lastname(cls, v: str | None) -> str | None:
        if v is None:
            return None

        return validators.validate_lastname(v)

    @field_validator("middlename")
    @classmethod
    def _validate_middlename(cls, v: str | None) -> str | None:
        if v is None:
            return None

        return validators.validate_middlename(v)

    @field_validator("phone_number", mode="after")
    @classmethod
    def _validate_phone_number(cls, v: str | None) -> str | None:
        if v is None:
            return None

        return validators.validate_phone_number(v)


class UpdateStaffOrGuardianAdmin(UpdateUserBase):
    type: Literal["staff_or_guardian"] = "staff_or_guardian"


class UpdateStudentAdmin(UpdateUserBase):
    type: Literal["student"] = "student"

    date_of_birth: date | None = None
    address: str | None = Field(min_length=15, max_length=100, default=None)

    @field_validator("date_of_birth", mode="after")
    @classmethod
    def _validate_date_of_birth(cls, v: date | None) -> date | None:
        if v is None:
            return None

        return validators.validate_date_of_birth(v)


UpdateUserRequest = Annotated[
    UpdateStaffOrGuardianAdmin | UpdateStudentAdmin,
    Field(discriminator="type"),
]


class UpdateUserCredentials(BaseModel):
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


class SearchUserBase(BaseModel):
    firstname: str | None = Field(min_length=2, max_length=50, default=None)
    lastname: str | None = Field(min_length=2, max_length=50, default=None)
    phone_number: str | None = Field(min_length=6, max_length=20, default=None)
    email: str | None = Field(min_length=3, max_length=100, default=None)
    status: UserStatus | None = None
