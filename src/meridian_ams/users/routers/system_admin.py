from fastapi import APIRouter, Request, status

from meridian_ams.core.dependencies import db_session_dependency, require_system_admin
from meridian_ams.users.schemas.system_admin import (
    CreateUserRequest,
    UserResponseDetailedAdmin,
)
from meridian_ams.users.services.system_admin import UserServiceAdmin

router = APIRouter(
    prefix="/api/v1/admin/users",
    tags=["Users - System Admin"],
)


@router.post(
    "",
    response_model=UserResponseDetailedAdmin,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    request: Request,
    db_session: db_session_dependency,
    current_user: require_system_admin,
    payload: CreateUserRequest,
):
    return await UserServiceAdmin.register_user(
        request, db_session, current_user.credentials_id, payload
    )
