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