from fastapi import APIRouter, Request, status

from src.core.dependencies import (
    require_guardian,
    session_dependency,
)
from src.core.limiter import user_limiter
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
