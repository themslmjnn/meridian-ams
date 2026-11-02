from sqlalchemy.exc import IntegrityError

from meridian_ams.core.exceptions import AppException


# HTTP404
class IdentityNotFoundError(AppException):
    status_code = 404
    detail = "Identity not found"
    error_code = "IDENTITY_NOT_FOUND"


# HTTP409
class UsernameAlreadyTakenError(AppException):
    status_code = 409
    detail = "Username already exists"
    error_code = "USERNAME_ALREADY_EXISTS"


class DuplicatePhoneNumberError(AppException):
    status_code = 409
    detail = "Phone number already exists"
    error_code = "DUPLICATE_PHONE"


class DuplicateEmailError(AppException):
    status_code = 409
    detail = "Email already exists"
    error_code = "DUPLICATE_EMAIL"


class MaxStudentsPerPhoneNumberError(AppException):
    status_code = 409
    detail = "Maximum number of students with this phone number reached"
    error_code = "MAX_STUDENTS_PER_PHONE_NUMBER"


class MaxStudentsPerEmailError(AppException):
    status_code = 409
    detail = "Maximum number of students with this email reached"
    error_code = "MAX_STUDENTS_PER_EMAIL"


class GuardianAccountAlreadyExistsError(AppException):
    status_code = 409
    detail = "Guardian account already exists"
    error_code = "DUPLICATE_ALREADY_GUARDIAN_ACCOUNT"


def handle_username_integrity_error(error: IntegrityError) -> None:
    if "uq_user_credentials_username" in str(error.orig):
        raise UsernameAlreadyTakenError()


def handle_non_student_unique_email_error(error: IntegrityError) -> None:
    if "uix_non_student_unique_email" in str(error.orig):
        raise DuplicateEmailError()


def handle_account_per_identity_error(error: IntegrityError) -> None:
    if "uix_one_personal_account_per_identity" in str(error.orig):
        raise GuardianAccountAlreadyExistsError()
