from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from src.users.utils.enums import UserRole


@dataclass
class LoadOptionsSchema:
    load_identity: bool = False
    load_sessions: bool = False
    load_activation: bool = False
    load_login_lockout: bool = False
    load_email_change: bool = False
    load_password_reset: bool = False


class UserResponseBase(BaseModel):
    firstname: str
    lastname: str
    middlename: str | None

    phone_number: str

    role: UserRole

    model_config = ConfigDict(extra="ignore")
