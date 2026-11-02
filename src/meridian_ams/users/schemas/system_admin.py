import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from meridian_ams.users.utils.enums import AccountType, UserRole, UserStatus
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
