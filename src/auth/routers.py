from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from src.auth.schemas import (
    ActivateAccount,
    LoginResponse,
    PasswordResetRequestPublic,
    ResetPassword,
)
from src.auth.service import AuthService
from src.core.dependencies import (
    current_user_dependency,
    db_session_dependency,
    redis_dependency,
)
from src.core.limiter import ip_limiter
from src.utils.exceptions import InvalidRefreshTokenError

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Auth"],
)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
@ip_limiter.limit("10/minute")
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


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    response: Response,
    db_session: db_session_dependency,
    redis: redis_dependency,
    current_user: current_user_dependency,
):
    await AuthService.logout(response, db_session, redis, current_user)


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout_all(
    response: Response,
    db_session: db_session_dependency,
    redis: redis_dependency,
    current_user: current_user_dependency,
) -> None:
    await AuthService.logout_all(db_session, redis, response, current_user)


@router.post(
    "/refresh-token",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
@ip_limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    redis: redis_dependency,
    refresh_token: str | None = Cookie(default=None),
):
    if refresh_token is None:
        raise InvalidRefreshTokenError()

    return await AuthService.refresh_token(response, db_session, redis, refresh_token)


@router.post(
    "/activation",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
@ip_limiter.limit("3/minute")
async def activate_account(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    payload: ActivateAccount,
):
    return await AuthService.activate_account(
        response,
        db_session,
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )


@router.post(
    "/password-reset",
    status_code=status.HTTP_204_NO_CONTENT,
)
@ip_limiter.limit("5/minute")
async def request_password_reset(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    payload: PasswordResetRequestPublic,
):
    await AuthService.request_password_reset(db_session, payload)


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
)
@ip_limiter.limit("5/minute")
async def reset_password(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    redis: redis_dependency,
    payload: ResetPassword,
):
    await AuthService.reset_password(db_session, redis, payload)
