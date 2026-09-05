import uuid
from datetime import date, datetime

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
