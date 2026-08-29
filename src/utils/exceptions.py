from sqlalchemy.exc import IntegrityError

from src.core.exceptions import AppException
from src.utils.constants import HTTP401


class InvalidAccessTokenError(AppException):
    status_code = 401
    detail = HTTP401.INVALID_ACCESS_TOKEN
    error_code = "INVALID_ACCESS_TOKEN"


class ExpiredAccessTokenError(AppException):
    status_code = 401
    detail = HTTP401.EXPIRED_ACCESS_TOKEN
    error = "EXPIRED_ACCESS_TOKEN"


class InvalidTokenTypeError(AppException):
    status_code = 401
    detail = HTTP401.INVALID_TOKEN_TYPE
    error_code = "INVALID_TOKEN_TYPE"


def raise_unhandled_integrity_error(error: IntegrityError) -> None:
    raise error
