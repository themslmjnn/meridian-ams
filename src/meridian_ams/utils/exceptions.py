from meridian_ams.core.exceptions import AppException


# HTTP401
class InvalidAccessTokenError(AppException):
    status_code = 401
    detail = "Invalid access token"
    error_code = "INVALID_ACCESS_TOKEN"


class ExpiredAccessTokenError(AppException):
    status_code = 401
    detail = "Expired access token"
    error_code = "EXPIRED_ACCESS_TOKEN"


class InvalidRefreshTokenError(AppException):
    status_code = 401
    detail = "Invalid refresh token"
    error_code = "INVALID_REFRESH_TOKEN"


class ExpiredRefreshTokenError(AppException):
    status_code = 401
    detail = "Expired refresh token"
    error_code = "EXPIRED_REFRESH_TOKEN"


class InvalidTokenTypeError(AppException):
    status_code = 401
    detail = "Invalid token type"
    error_code = "INVALID_TOKEN_TYPE"


class InvalidCredentialsError(AppException):
    status_code = 401
    detail = "Invalid credentials"
    error_code = "INVALID_CREDENTIALS"


# HTTP403
class AccessDeniedError(AppException):
    status_code = 403
    detail = "Access denied"
    error_code = "ACCESS_DENIED"


class AccountLockedError(AppException):
    status_code = 403
    error_code = "ACCOUNT_LOCKED"
    detail = "Your account is locked"


class AccountNotActivatedError(AppException):
    status_code = 403
    detail = "Account has not been activated yet"
    error_code = "ACCOUNT_NOT_ACTIVATED"


class AccountInactiveError(AppException):
    status_code = 403
    detail = "Account is inactive"
    error_code = "ACCOUNT_INACTIVE"


class AccountGraduatedError(AppException):
    status_code = 403
    detail = "This account belongs to a graduated student"
    error_code = "ACCOUNT_GRADUATED"


class AccountExpelledError(AppException):
    status_code = 403
    detail = "This account has been expelled"
    error_code = "ACCOUNT_EXPELLED"


class AccountWithdrawnError(AppException):
    status_code = 403
    detail = "This account has been withdrawn"
    error_code = "ACCOUNT_WITHDRAWN"
