from fastapi import Response

from src.core.config import get_settings

settings = get_settings()

_COOKIE_PATH_REFRESH = "/api/v1/auth/refresh-token"
_COOKIE_PATH_LOGIN = "/api/v1/auth/login"


def set_refresh_token_cookie(response: Response, raw_refresh_token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=raw_refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRES_DAYS,
        path=_COOKIE_PATH_REFRESH,
    )


def clear_refresh_token_cookie(response: Response) -> None:
    response.delete_cookie(
        key="refresh_token",
        path=_COOKIE_PATH_REFRESH,
    )


def set_refresh_token_family_cookie(
    response: Response, raw_refresh_token_family: str
) -> None:
    response.set_cookie(
        key="refresh_token_family",
        value=raw_refresh_token_family,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRES_DAYS,
        path=_COOKIE_PATH_REFRESH,
    )


def clear_refresh_token_family_cookie(response: Response) -> None:
    response.delete_cookie(
        key="refresh_token_family",
        path=_COOKIE_PATH_REFRESH,
    )


def set_device_id_cookie(response: Response, device_id: str) -> None:
    response.set_cookie(
        key="device_id",
        value=device_id,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRES_DAYS,
        path=_COOKIE_PATH_LOGIN,
    )


def clear_device_id_cookie(response: Response) -> None:
    response.delete_cookie(
        key="device_id",
        path=_COOKIE_PATH_LOGIN,
    )
