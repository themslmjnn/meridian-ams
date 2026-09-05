import uuid
from datetime import date, datetime

from pydantic import BaseModel

from src.users.utils.enums import UserRole, UserStatus
from src.utils.base_schema import BaseSchema


class UserResponseBase(BaseModel):
    firstname: str
    lastname: str
    middlename: str | None


class UserResponseDirectorDetailed(UserResponseBase, BaseSchema):
    date_of_birth: date | None
    address: str | None

    public_id: uuid.UUID

    username: str
    phone_number: str
    email: str

    role: UserRole
    status: UserStatus

    created_at: datetime
