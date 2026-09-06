from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from src.auth.schemas import (
    ActivateAccount,
    ForgotPasswordRequest,
    LoginResponse,
    ResetPasswordRequest,
)
from src.auth.service import AuthService
from src.core.dependencies import (
    current_user_dependency,
    redis_dependency,
    session_dependency,
)
from src.utils.exceptions import InvalidRefreshTokenError

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Auth"],
)


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    request: Request,
    response: Response,
    session: session_dependency,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    return await AuthService.login(
        session=session,
        request=request,
        response=response,
        form_data=form_data,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session: session_dependency,
    redis: redis_dependency,
    current_user: current_user_dependency,
) -> None:
    await AuthService.logout(session, redis, response, current_user)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    response: Response,
    session: session_dependency,
    redis: redis_dependency,
    current_user: current_user_dependency,
) -> None:
    await AuthService.logout_all(session, redis, response, current_user)


@router.post(
    "/refresh-token", response_model=LoginResponse, status_code=status.HTTP_200_OK
)
async def refresh_token(
    request: Request,
    response: Response,
    session: session_dependency,
    refresh_token: str | None = Cookie(default=None),
    refresh_token_family: str | None = Cookie(default=None),
):
    if refresh_token is None or refresh_token_family is None:
        raise InvalidRefreshTokenError()

    return await AuthService.refresh_token(
        request, response, session, refresh_token, refresh_token_family
    )


@router.post(
    "/activation", response_model=LoginResponse, status_code=status.HTTP_200_OK
)
async def activate(
    request: Request,
    response: Response,
    session: session_dependency,
    payload: ActivateAccount,
):
    return await AuthService.activate_account(
        response,
        session,
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    session: session_dependency,
    payload: ForgotPasswordRequest,
):
    await AuthService.forgot_password(session, payload)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    request: Request,
    session: session_dependency,
    payload: ResetPasswordRequest,
):
    await AuthService.reset_password(request, session, payload)
