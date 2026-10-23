import uuid

from src.guardian_links.schemas.system_admin import PersonName
from src.guardian_links.utils.enums import GuardianType
from src.utils.base_schema import BaseSchema


class MyStudentLinkResponse(BaseSchema):
    student_public_id: uuid.UUID
    student: PersonName
    guardian_type: GuardianType


class MyGuardianLinkResponse(BaseSchema):
    guardian: PersonName
    guardian_type: GuardianType
