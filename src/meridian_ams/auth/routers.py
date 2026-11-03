from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from meridian_ams.auth.schemas import LoginResponse
from meridian_ams.auth.services import AuthService
from meridian_ams.core.dependencies import db_session_dependency, redis_dependency

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Auth"],
)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
async def login(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    redis: redis_dependency,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    return await AuthService.login(
        request,
        response,
        db_session,
        redis,
        form_data=form_data,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
