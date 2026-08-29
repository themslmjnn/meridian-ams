import uuid

from pydantic import BaseModel

from src.users.utils.enums import AccountType, UserRole


class CreateAccessToken(BaseModel):
    public_id: uuid.UUID
    role: UserRole
    account_type: AccountType
    session_id: int
    access_token_version: int
