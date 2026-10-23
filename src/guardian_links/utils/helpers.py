from src.guardian_links.schemas.system_admin import GuardianLinkResponse, PersonName
from src.guardian_links.utils.enums import GuardianType
from src.users.models.credentials import UserCredentials
from src.users.models.identity import UserIdentity


def build_person_name(identity: UserIdentity) -> PersonName:
    return PersonName(
        firstname=identity.firstname,
        lastname=identity.lastname,
        middlename=identity.middlename,
    )


def build_guardian_link_response(
    guardian: UserCredentials,
    student: UserCredentials,
    guardian_type: GuardianType,
) -> GuardianLinkResponse:
    return GuardianLinkResponse(
        guardian_public_id=guardian.public_id,
        guardian=build_person_name(guardian.identity),
        student_public_id=student.public_id,
        student=build_person_name(student.identity),
        guardian_type=guardian_type,
    )
