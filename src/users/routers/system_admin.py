import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from src.core.dependencies import CurrentUser, require_system_admin, session_dependency
from src.core.limiter import user_limiter
from src.users.schemas.system_admin import (
    CreateUserRequest,
    UpdateUserCredentials,
    UpdateUserRequest,
    UserResponseAdminDetailed,
)
from src.users.services.system_admin import UserServiceAdmin

router = APIRouter(
    prefix="/api/v1/admin/users",
    tags=["Users - System Admin"],
)


@router.post(
    "", response_model=UserResponseAdminDetailed, status_code=status.HTTP_201_CREATED
)
@user_limiter.limit("7/minute")
async def register_user(
    request: Request,
    session: session_dependency,
    current_user: require_system_admin,
    payload: CreateUserRequest,
):
    return await UserServiceAdmin.register_user(
        session, current_user.credentials_id, payload
    )


@router.patch(
    "/{public_id}/profile",
    status_code=status.HTTP_204_NO_CONTENT,
)
@user_limiter.limit("7/minute")
async def update_user(
    request: Request,
    session: session_dependency,
    current_user: require_system_admin,
    public_id: uuid.UUID,
    payload: UpdateUserRequest,
):
    await UserServiceAdmin.update_user(
        request, session, current_user.credentials_id, public_id, payload
    )


@router.patch(
    "/{public_id}/credentials",
    status_code=status.HTTP_204_NO_CONTENT,
)
@user_limiter.limit("5/minute")
async def update_user_credentials(
    request: Request,
    session: session_dependency,
    current_user: require_system_admin,
    public_id: uuid.UUID,
    payload: UpdateUserCredentials,
):
    await UserServiceAdmin.update_user_credentials(
        request, session, current_user.credentials_id, public_id, payload
    )


@router.patch("/{public_id}/deactivation", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit("5/minute")
async def deactivate_user(
    request: Request,
    session: session_dependency,
    current_user: require_system_admin,
    public_id: uuid.UUID,
):
    await UserServiceAdmin.deactivate_user(request, session, current_user.id, public_id)


@router.patch("/{public_id}/activation", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit("10/minute")
async def activate_user(
    request: Request,
    session: session_dependency,
    current_user: require_system_admin,
    public_id: uuid.UUID,
):
    await UserServiceAdmin.activate_user(request, session, current_user.id, public_id)


@router.post("/{public_id}/password", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit("5/minute")
async def create_reset_password_request(
    request: Request,
    session: session_dependency,
    current_user: require_system_admin,
    public_id: uuid.UUID,
):
    await UserServiceAdmin.create_reset_password_request(
        session, current_user.id, public_id
    )


@router.post(
    "/{public_id}/resend-invite",
    status_code=status.HTTP_204_NO_CONTENT,
)
@user_limiter.limit("5/minute")
async def resend_activation_invite(
    request: Request,
    session: session_dependency,
    current_user: require_system_admin,
    public_id: uuid.UUID,
):
    await UserServiceAdmin.resend_activation_invite(session, current_user.id, public_id)


@router.post(
    "/{public_id}/guardian-deletion",
    status_code=status.HTTP_204_NO_CONTENT,
)
@user_limiter.limit("3/minute")
async def create_guardian_deletion_request(
    request: Request,
    session: session_dependency,
    current_user: require_system_admin,
    public_id: uuid.UUID,
):
    await UserServiceAdmin.create_guardian_deletion_request(
        request, session, current_user.id, public_id
    )


@router.post(
    "/{public_id}/cancel-deletion",
    status_code=status.HTTP_204_NO_CONTENT,
)
@user_limiter.limit("3/minute")
async def cancel_guardian_deletion_request(
    request: Request,
    session: session_dependency,
    current_user: require_system_admin,
    public_id: uuid.UUID,
):
    await UserServiceAdmin.cancel_guardian_deletion_request(
        request, session, current_user.id, public_id
    )
