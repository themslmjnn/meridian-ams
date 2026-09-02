from sqlalchemy.exc import IntegrityError

from src.core.exceptions import AppException
from src.utils.constants import HTTP400, HTTP401, HTTP403


class InvalidAccessTokenError(AppException):
    status_code = 401
    detail = HTTP401.INVALID_ACCESS_TOKEN
    error_code = "INVALID_ACCESS_TOKEN"


class ExpiredAccessTokenError(AppException):
    status_code = 401
    detail = HTTP401.EXPIRED_ACCESS_TOKEN
    error_code = "EXPIRED_ACCESS_TOKEN"


class InvalidTokenTypeError(AppException):
    status_code = 401
    detail = HTTP401.INVALID_TOKEN_TYPE
    error_code = "INVALID_TOKEN_TYPE"


class AccessDeniedError(AppException):
    status_code = 403
    detail = HTTP403.ACCESS_DENIED
    error_code = "ACCESS_DENIED"


class InvalidCredentialsError(AppException):
    status_code = 401
    detail = HTTP401.INVALID_CREDENTIALS
    error_code = "INVALID_CREDENTIALS"


class AccountLockedError(AppException):
    status_code = 403
    error_code = "ACCOUNT_LOCKED"


class AccountInactiveError(AppException):
    status_code = 401
    detail = HTTP401.ACCOUNT_NOT_ACTIVATED
    error_code = "ACCOUNT_NOT_ACTIVATED"


class GracePeriodExpiredError(AppException):
    status_code = 401
    detail = HTTP401.ACCOUNT_DELETION_EXPIRED
    error_code = "ACCOUNT_DELETION_EXPIRED"


class NoChangesDetectedError(AppException):
    status_code = 400
    detail = HTTP400.NO_CHANGES_DETECTED
    error_code = "NO_CHANGES_DETECTED"


def raise_unhandled_integrity_error(error: IntegrityError) -> None:
    raise error
