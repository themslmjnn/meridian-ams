from collections.abc import Mapping
from typing import Any

from src.guardian_links.schemas.director import GuardianLinkResponseDirector
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


def build_guardian_link_response_from_row(
    row: Mapping[str, Any],
) -> GuardianLinkResponse:
    return GuardianLinkResponse(
        guardian_public_id=row["guardian_public_id"],
        guardian=PersonName(
            firstname=row["guardian_firstname"],
            lastname=row["guardian_lastname"],
            middlename=row["guardian_middlename"],
        ),
        student_public_id=row["student_public_id"],
        student=PersonName(
            firstname=row["student_firstname"],
            lastname=row["student_lastname"],
            middlename=row["student_middlename"],
        ),
        guardian_type=row["guardian_type"],
    )


def build_guardian_link_response_director_from_row(
    row: Mapping[str, Any],
) -> GuardianLinkResponseDirector:
    return GuardianLinkResponseDirector(
        guardian=PersonName(
            firstname=row["guardian_firstname"],
            lastname=row["guardian_lastname"],
            middlename=row["guardian_middlename"],
        ),
        student_public_id=row["student_public_id"],
        student=PersonName(
            firstname=row["student_firstname"],
            lastname=row["student_lastname"],
            middlename=row["student_middlename"],
        ),
        guardian_type=row["guardian_type"],
    )
