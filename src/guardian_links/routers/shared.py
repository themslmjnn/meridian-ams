from fastapi import APIRouter, status

from src.core.dependencies import (
    db_session_dependency,
    require_guardian,
    require_student,
)
from src.guardian_links.schemas.shared import (
    MyGuardianLinkResponse,
    MyStudentLinkResponse,
)
from src.guardian_links.services.shared import GuardianLinkServiceShared

router = APIRouter(
    prefix="/api/v1/users/me",
    tags=["Guardian Links - Self Service"],
)


@router.get(
    "/guardian-links",
    response_model=list[MyStudentLinkResponse],
    status_code=status.HTTP_200_OK,
)
async def get_my_students(
    db_session: db_session_dependency,
    current_user: require_guardian,
):
    return await GuardianLinkServiceShared.get_my_students(
        db_session, current_user.credentials_id
    )


@router.get(
    "/guardians",
    response_model=list[MyGuardianLinkResponse],
    status_code=status.HTTP_200_OK,
)
async def get_my_guardians(
    db_session: db_session_dependency,
    current_user: require_student,
):
    return await GuardianLinkServiceShared.get_my_guardians(
        db_session, current_user.credentials_id
    )
