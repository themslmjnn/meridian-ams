import uuid
from dataclasses import dataclass

from pydantic import BaseModel

from src.users.utils.enums import AccountType, UserRole


class CreateAccessToken(BaseModel):
    public_id: uuid.UUID
    role: UserRole
    account_type: AccountType
    session_id: int
    access_token_version: int


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@dataclass
class CreateRefreshToken:
    public_id: uuid.UUID
    session_id: int
