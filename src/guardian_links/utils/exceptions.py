from sqlalchemy.exc import IntegrityError

from src.core.exceptions import AppException
from src.guardian_links.utils.constants import HTTP400, HTTP404, HTTP409


# HTTP400
class InvalidGuardianAccountError(AppException):
    status_code = 400
    detail = HTTP400.INVALID_GUARDIAN_ACCOUNT
    error_code = "INVALID_GUARDIAN_ACCOUNT"


class InvalidStudentAccountError(AppException):
    status_code = 400
    detail = HTTP400.INVALID_STUDENT_ACCOUNT
    error_code = "INVALID_STUDENT_ACCOUNT"


class InvalidStudentStatusError(AppException):
    status_code = 400
    detail = HTTP400.INVALID_STUDENT_STATUS
    error_code = "INVALID_STUDENT_STATUS"


# HTTP404
class GuardianNotFoundError(AppException):
    status_code = 404
    detail = HTTP404.GUARDIAN_NOT_FOUND
    error_code = "GUARDIAN_NOT_FOUND"


class StudentNotFoundError(AppException):
    status_code = 404
    detail = HTTP404.STUDENT_NOT_FOUND
    error_code = "STUDENT_NOT_FOUND"


# HTTP409
class GuardianAlreadyLinkedError(AppException):
    status_code = 409
    detail = HTTP409.GUARDIAN_ALREADY_LINKED
    error_code = "GUARDIAN_ALREADY_LINKED"


class GuardianTypeTakenError(AppException):
    status_code = 409
    detail = HTTP409.GUARDIAN_TYPE_TAKEN
    error_code = "GUARDIAN_TYPE_TAKEN"


def handle_duplicate_link_error(error: IntegrityError):
    if "uix_no_duplicate_guardian_link" in str(error.orig):
        raise GuardianAlreadyLinkedError()


def handle_guardian_type_error(error: IntegrityError):
    if "uix_one_guardian_type_per_student" in str(error.orig):
        raise GuardianTypeTakenError()
