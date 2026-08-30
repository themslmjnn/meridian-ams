from src.core.exceptions import AppException
from src.emails.utils.constants import HTTP404


class EmailNotFoundError(AppException):
    status_code = 404
    detail = HTTP404.EMAIL
    error_code = "EMAIL_NOT_FOUND"
