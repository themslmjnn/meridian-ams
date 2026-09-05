from fastapi import APIRouter, Request, status

from src.core.dependencies import (
    require_guardian,
    session_dependency,
)
from src.core.limiter import user_limiter
from src.users.schemas.guardian import UpdateProfileGuardian
from src.users.services.guardian import UserServiceGuardian

router = APIRouter(
    tags=["Users - Guardian"],
)


@router.post("/api/v1/admin/users/me/deletion", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit("3/minute")
async def create_guardian_self_deletion_request(
    request: Request,
    session: session_dependency,
    current_user: require_guardian,
):
    await UserServiceGuardian.create_guardian_self_deletion_request(
        request, session, current_user.credentials_id
    )


@router.patch(
    "/me/profile",
    status_code=status.HTTP_204_NO_CONTENT,
)
@user_limiter.limit("10/minute")
async def update_me_profile(
    request: Request,
    session: session_dependency,
    current_user: require_guardian,
    payload: UpdateProfileGuardian,
):
    await UserServiceGuardian.update_profile(request, session, current_user, payload)
