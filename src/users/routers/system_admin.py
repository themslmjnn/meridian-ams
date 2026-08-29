from fastapi import APIRouter, status

from src.core.dependencies import session_dependency
from src.users.schemas.system_admin import CreateUserRequest, UserResponseAdminDetailed
from src.users.services.system_admin import UserServiceAdmin

router = APIRouter(
    prefix="/api/v1/admin/users",
    tags=["Users - System Admin"],
)


@router.post(
    "", response_model=UserResponseAdminDetailed, status_code=status.HTTP_201_CREATED
)
async def register_user(
    session: session_dependency,
    create_request: CreateUserRequest,
):
    return await UserServiceAdmin.register_user(session, 1, create_request)
