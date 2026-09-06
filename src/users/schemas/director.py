import uuid
from datetime import date, datetime

from src.users.utils.enums import UserRole, UserStatus
from src.users.utils.schemas import UserResponseBase
from src.utils.base_schema import BaseSchema


class UserResponseDirectorDetailed(UserResponseBase, BaseSchema):
    date_of_birth: date | None
    address: str | None

    public_id: uuid.UUID

    username: str
    email: str

    role: UserRole
    status: UserStatus

    created_at: datetime
