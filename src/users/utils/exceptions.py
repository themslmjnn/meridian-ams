from sqlalchemy.exc import IntegrityError

from src.core.exceptions import AppException
from src.users.utils.constants import HTTP409


class UsernameAlreadyTakenError(AppException):
    status_code = 409
    detail = HTTP409.USERNAME
    error_code = "USERNAME_ALREADY_TAKEN"


class MaxStudentsPerPhoneNumberError(AppException):
    status_code = 409
    detail = HTTP409.MAX_STUDENTS_PER_PHONE
    error_code = "MAX_STUDENTS_PER_PHONE_NUMBER"


class MaxStudentsPerEmailError(AppException):
    status_code = 409
    detail = HTTP409.MAX_STUDENTS_PER_EMAIL
    error_code = "MAX_STUDENTS_PER_EMAIL"


class DuplicatePhoneNumberError(AppException):
    status_code = 409
    detail = HTTP409.DUPLICATE_PHONE_NUMBER
    error_code = "DUPLICATE_PHONE_NUMBER"


class PhoneNumberAlreadyExistsError(AppException):
    status_code = 409


class DuplicateEmailError(AppException):
    status_code = 409
    detail = HTTP409.DUPLICATE_PHONE_NUMBER
    error_code = "DUPLICATE_PHONE_NUMBER"


class IdentityNotFoundError(AppException):
    status_code = 404
    detail = "No identity found with the provided ID"
    error_code = "IDENTITY_NOT_FOUND"


def handle_username_integrity_error(error: IntegrityError) -> None:
    if "user_credentials_username_key" in str(error.orig):
        raise UsernameAlreadyTakenError()


def handle_non_student_unique_contact_error(error: IntegrityError) -> None:
    error_detail = str(error.orig)

    if "uix_non_student_unique_email" in error_detail:
        raise DuplicateEmailError()
