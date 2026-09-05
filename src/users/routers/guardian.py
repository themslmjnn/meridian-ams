from fastapi import APIRouter, Request, status

from src.core.dependencies import (
    redis_dependency,
    require_guardian,
    session_dependency,
)
from src.core.limiter import user_limiter
from src.users.schemas.guardian import UpdateProfileGuardian
from src.users.services.guardian import UserServiceGuardian

router = APIRouter(
    prefix="/api/v1/users/me",
    tags=["Users - Guardian"],
)


@router.post("/deletion", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit("3/minute")
async def create_guardian_self_deletion_request(
    request: Request,
    session: session_dependency,
    redis: redis_dependency,
    current_user: require_guardian,
):
    await UserServiceGuardian.create_guardian_self_deletion_request(
        session, redis, current_user.credentials_id
    )


@router.patch(
    "/profile",
    status_code=status.HTTP_204_NO_CONTENT,
)
@user_limiter.limit("10/minute")
async def update_me_profile(
    request: Request,
    session: session_dependency,
    redis: redis_dependency,
    current_user: require_guardian,
    payload: UpdateProfileGuardian,
):
    await UserServiceGuardian.update_profile(session, redis, current_user, payload)
