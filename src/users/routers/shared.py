from fastapi import APIRouter, Request, status

from src.core.dependencies import (
    current_user_dependency,
    session_dependency,
)
from src.users.schemas.shared import UserResponseSelf
from src.users.services.shared import UserServiceSelf

router = APIRouter(
    prefix="/api/v1/users",
    tags=["Users - Shared"],
)


@router.get("/me", response_model=UserResponseSelf, status_code=status.HTTP_200_OK)
async def get_my_profile(
    request: Request,
    session: session_dependency,
    current_user: current_user_dependency,
):
    return await UserServiceSelf.get_my_profile(request, session, current_user)
