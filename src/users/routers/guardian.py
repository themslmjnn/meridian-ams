from fastapi import APIRouter, Request, Response, status

from src.core.dependencies import (
    db_session_dependency,
    redis_dependency,
    require_guardian,
)
from src.core.limiter import user_limiter
from src.users.services.guardian import UserServiceGuardian

router = APIRouter(
    prefix="/api/v1/users/me",
    tags=["Users - Guardian"],
)


@router.post("/deletion-request", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit("3/minute")
async def create_guardian_self_deletion_request(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    redis: redis_dependency,
    current_user: require_guardian,
):
    await UserServiceGuardian.create_guardian_self_deletion_request(
        db_session, redis, current_user.credentials_id
    )
