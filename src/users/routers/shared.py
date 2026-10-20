from fastapi import APIRouter, Request, Response, status

from src.core.dependencies import (
    current_user_dependency,
    db_session_dependency,
    redis_dependency,
    require_admin_and_guardian,
)
from src.core.limiter import user_limiter
from src.users.schemas.shared import (
    ConfirmEmailChange,
    UpdateMePassword,
    UpdateMeProfile,
    UserResponseSelf,
)
from src.users.services.shared import UserServiceSelf
from src.users.utils.schemas import UpdateCredentials

router = APIRouter(
    prefix="/api/v1/users",
    tags=["Users - Shared"],
)


@router.get(
    "/me",
    response_model=UserResponseSelf,
    status_code=status.HTTP_200_OK,
)
async def get_my_profile(
    db_session: db_session_dependency,
    redis: redis_dependency,
    current_user: current_user_dependency,
):
    return await UserServiceSelf.get_my_profile(db_session, redis, current_user)


@router.patch(
    "/me/credentials",
    status_code=status.HTTP_204_NO_CONTENT,
)
@user_limiter.limit("5/minute")
async def update_me_credentials(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    redis: redis_dependency,
    current_user: current_user_dependency,
    payload: UpdateCredentials,
):
    await UserServiceSelf.update_me_credentials(
        db_session, redis, current_user, payload
    )


@router.post(
    "/me/credentials/confirm-email",
    status_code=status.HTTP_204_NO_CONTENT,
)
@user_limiter.limit("5/minute")
async def confirm_email_change(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    redis: redis_dependency,
    current_user: current_user_dependency,
    payload: ConfirmEmailChange,
):
    await UserServiceSelf.confirm_email_change(db_session, redis, current_user, payload)


@router.patch(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
)
@user_limiter.limit("5/minute")
async def update_me_password(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    redis: redis_dependency,
    current_user: current_user_dependency,
    payload: UpdateMePassword,
):
    await UserServiceSelf.update_me_password(db_session, redis, current_user, payload)


@router.patch("/profile", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit("10/minute")
async def update_me_profile(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    redis: redis_dependency,
    current_user: require_admin_and_guardian,
    payload: UpdateMeProfile,
):
    await UserServiceSelf.update_me_profile(db_session, redis, current_user, payload)
