from fastapi import APIRouter, Request, status

from src.core.dependencies import (
    current_user_dependency,
    redis_dependency,
    session_dependency,
)
from src.core.limiter import user_limiter
from src.users.schemas.shared import (
    ConfirmEmailChange,
    UpdateMePassword,
    UpdateUserCredentials,
    UserResponseSelf,
)
from src.users.services.shared import UserServiceSelf

router = APIRouter(
    prefix="/api/v1/users",
    tags=["Users - Shared"],
)


@router.get("/me", response_model=UserResponseSelf, status_code=status.HTTP_200_OK)
async def get_my_profile(
    session: session_dependency,
    redis: redis_dependency,
    current_user: current_user_dependency,
):
    return await UserServiceSelf.get_my_profile(session, redis, current_user)


@router.patch(
    "/me/credentials",
    status_code=status.HTTP_204_NO_CONTENT,
)
@user_limiter.limit("5/minute")
async def update_me_credentials(
    request: Request,
    session: session_dependency,
    redis: redis_dependency,
    current_user: current_user_dependency,
    update_request: UpdateUserCredentials,
):
    await UserServiceSelf.update_me_credentials(
        session, redis, current_user, update_request
    )


@router.post(
    "/me/credentials/confirm-email",
    status_code=status.HTTP_204_NO_CONTENT,
)
@user_limiter.limit("5/minute")
async def confirm_email_change(
    request: Request,
    session: session_dependency,
    redis: redis_dependency,
    current_user: current_user_dependency,
    confirm_request: ConfirmEmailChange,
):
    await UserServiceSelf.confirm_email_change(
        session, redis, current_user, confirm_request
    )


@router.patch(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
)
@user_limiter.limit("5/minute")
async def update_me_password(
    request: Request,
    session: session_dependency,
    redis: redis_dependency,
    current_user: current_user_dependency,
    update_request: UpdateMePassword,
):
    await UserServiceSelf.update_me_password(
        session, redis, current_user.id, update_request
    )
