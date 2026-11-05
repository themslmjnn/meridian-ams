from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from meridian_ams.core.dependencies import (
    db_session_dependency,
    redis_dependency,
    require_system_admin,
)
from meridian_ams.core.idempotency.service import make_idempotency_key_dependency
from meridian_ams.core.limiter import get_user_identifier, limiter
from meridian_ams.users.schemas.system_admin import (
    CreateUserRequest,
    UserResponseDetailedAdmin,
)
from meridian_ams.users.use_cases.register_user import RegisterUserUseCase

router = APIRouter(
    prefix="/admin/users",
    tags=["Users - System Admin"],
)


@router.post(
    "",
    response_model=UserResponseDetailedAdmin,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def register_user(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    redis: redis_dependency,
    current_user: require_system_admin,
    payload: CreateUserRequest,
    idempotency_key: Annotated[str, Depends(make_idempotency_key_dependency())],
):
    return await RegisterUserUseCase.execute(
        db_session,
        redis,
        current_user.credentials_id,
        payload,
        idempotency_key,
    )
