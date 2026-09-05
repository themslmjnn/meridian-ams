from sqlalchemy.exc import IntegrityError

from src.core.exceptions import AppException
from src.users.utils.constants import HTTP400, HTTP404, HTTP409


class UsernameAlreadyTakenError(AppException):
    status_code = 409
    detail = HTTP409.DUPLICATE_USERNAME
    error_code = "USERNAME_ALREADY_TAKEN"


class MaxStudentsPerPhoneNumberError(AppException):
    status_code = 409
    detail = HTTP409.MAX_STUDENTS_PER_PHONE_NUMBER
    error_code = "MAX_STUDENTS_PER_PHONE_NUMBER"


class MaxStudentsPerEmailError(AppException):
    status_code = 409
    detail = HTTP409.MAX_STUDENTS_PER_EMAIL
    error_code = "MAX_STUDENTS_PER_EMAIL"


class DuplicatePhoneNumberError(AppException):
    status_code = 409
    detail = HTTP409.DUPLICATE_PHONE_NUMBER
    error_code = "DUPLICATE_PHONE_NUMBER"


class DuplicateEmailError(AppException):
    status_code = 409
    detail = HTTP409.DUPLICATE_EMAIL
    error_code = "DUPLICATE_EMAIL"


class IdentityNotFoundError(AppException):
    status_code = 404
    detail = HTTP404.IDENTITY
    error_code = "IDENTITY_NOT_FOUND"


class GuardianAccountAlreadyExistsError(AppException):
    status_code = 409
    detail = HTTP409.DUPLICATE_GUARDIAN_ACCOUNT
    error_code = "GUARDIAN_ACCOUNT_ALREADY_EXISTS"


class CredentialsNotFoundError(AppException):
    status_code = 404
    detail = HTTP404.CREDENTIALS
    error_code = "CREDENTIALS_NOT_FOUND"


class UserNotFoundError(AppException):
    status_code = 404
    detail = HTTP404.User
    error_code = "USER_NOT_FOUND"


class UserTypeMismatchError(AppException):
    status_code = 400
    detail = HTTP400.USER_TYPE_MISMATCH
    error_code = "USER_TYPE_MISMATCH"


class UserAlreadyInactiveError(AppException):
    status_code = 409
    detail = HTTP409.USER_INACTIVE
    error_code = "USER_ALREADY_INACTIVE"


class UserAlreadyActiveError(AppException):
    status_code = 409
    detail = HTTP409.USER_ACTIVE
    error_code = "USER_ALREADY_ACTIVE"


class UserNotPendingActivationError(AppException):
    status_code = 409
    detail = HTTP409.USER_ACTIVE
    error_code = "USER_ALREADY_ACTIVE"


class GuardianAlreadyPendingDeletionError(AppException):
    status_code = 409
    detail = HTTP409.PENDING_DELETION
    error_code = "PENDING_DELETION"


class InvalidStatusTransitionError(AppException):
    status_code = 403
    detail = "Invalid status transition"
    error_code = "INVALID_STATUS_TRANSITION"


def handle_username_integrity_error(error: IntegrityError) -> None:
    if "user_credentials_username_key" in str(error.orig):
        raise UsernameAlreadyTakenError()


def handle_non_student_unique_contact_error(error: IntegrityError) -> None:
    error_detail = str(error.orig)

    if "uix_non_student_unique_email" in error_detail:
        raise DuplicateEmailError()

    if "uix_one_personal_account_per_identity" in error_detail:
        raise GuardianAccountAlreadyExistsError()
