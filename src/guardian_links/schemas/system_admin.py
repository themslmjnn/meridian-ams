import uuid

from pydantic import BaseModel

from src.guardian_links.utils.enums import GuardianType
from src.utils.base_schema import BaseSchema


class CreateGuardianLink(BaseModel):
    guardian_public_id: uuid.UUID
    student_public_id: uuid.UUID
    guardian_type: GuardianType


class PersonName(BaseSchema):
    firstname: str
    lastname: str
    middlename: str | None


class GuardianLinkResponse(BaseSchema):
    guardian_public_id: uuid.UUID
    guardian: PersonName
    student_public_id: uuid.UUID
    student: PersonName
    guardian_type: GuardianType


class SearchGuardianLink(BaseModel):
    guardian_type: GuardianType | None = None
    guardian_firstname: str | None = None
    guardian_lastname: str | None = None
    student_firstname: str | None = None
    student_lastname: str | None = None
