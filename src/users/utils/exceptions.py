from sqlalchemy.exc import IntegrityError

from src.core.exceptions import AppException
from src.users.utils.constants import HTTP400, HTTP403, HTTP404, HTTP409


# HTTP400
class UpdatePayloadMismatchError(AppException):
    status_code = 400
    detail = HTTP400.UPDATE_PAYLOAD_MISMATCH
    error_code = "UPDATE_PAYLOAD_MISMATCH"


class InvalidEmailChangeCodeError(AppException):
    status_code = 400
    detail = HTTP400.INVALID_EMAIL_CHANGE_CODE
    error_code = "INVALID_EMAIL_CHANGE_CODE"


class EmailChangeCodeExpiredError(AppException):
    status_code = 400
    detail = HTTP400.EXPIRED_EMAIL_CHANGE_CODE
    error_code = "EXPIRED_EMAIL_CHANGE_CODE"


class IncorrectPasswordError(AppException):
    status_code = 400
    detail = HTTP400.INCORRECT_PASSWORD
    error_code = "INCORRECT_PASSWORD"


# HTTP403
class InvalidStatusTransitionError(AppException):
    status_code = 403
    detail = HTTP403.INVALID_STATUS_TRANSITION
    error_code = "INVALID_STATUS_TRANSITION"


# HTTP404
class IdentityNotFoundError(AppException):
    status_code = 404
    detail = HTTP404.IDENTITY
    error_code = "IDENTITY_NOT_FOUND"


class CredentialsNotFoundError(AppException):
    status_code = 404
    detail = HTTP404.CREDENTIALS
    error_code = "CREDENTIALS_NOT_FOUND"


class UserNotFoundError(AppException):
    status_code = 404
    detail = HTTP404.USER
    error_code = "USER_NOT_FOUND"


class NoPendingEmailChangeError(AppException):
    status_code = 404
    detail = HTTP404.NO_PENDING_EMAIL_CHANGE
    error_code = "NO_PENDING_EMAIL_CHANGE"


# HTTP409
class UsernameAlreadyTakenError(AppException):
    status_code = 409
    detail = HTTP409.DUPLICATE_USERNAME
    error_code = "USERNAME_ALREADY_TAKEN"


class DuplicatePhoneNumberError(AppException):
    status_code = 409
    detail = HTTP409.DUPLICATE_PHONE_NUMBER
    error_code = "DUPLICATE_PHONE_NUMBER"


class DuplicateEmailError(AppException):
    status_code = 409
    detail = HTTP409.DUPLICATE_EMAIL
    error_code = "DUPLICATE_EMAIL"


class MaxStudentsPerPhoneNumberError(AppException):
    status_code = 409
    detail = HTTP409.MAX_STUDENTS_PER_PHONE_NUMBER
    error_code = "MAX_STUDENTS_PER_PHONE_NUMBER"


class MaxStudentsPerEmailError(AppException):
    status_code = 409
    detail = HTTP409.MAX_STUDENTS_PER_EMAIL
    error_code = "MAX_STUDENTS_PER_EMAIL"


class GuardianAccountAlreadyExistsError(AppException):
    status_code = 409
    detail = HTTP409.DUPLICATE_GUARDIAN_ACCOUNT
    error_code = "DUPLICATE_GUARDIAN_ACCOUNT"


class UserAlreadyInactiveError(AppException):
    status_code = 409
    detail = HTTP409.USER_ALREADY_INACTIVE
    error_code = "USER_ALREADY_INACTIVE"


class UserAlreadyActiveError(AppException):
    status_code = 409
    detail = HTTP409.USER_ALREADY_ACTIVE
    error_code = "USER_ALREADY_ACTIVE"


class UserNotPendingActivationError(AppException):
    status_code = 409
    detail = HTTP409.USER_NOT_PENDING_ACTIVATION
    error_code = "USER_NOT_PENDING_ACTIVATION"


class GuardianAlreadyPendingDeletionError(AppException):
    status_code = 409
    detail = HTTP409.GUARDIAN_PENDING_DELETION
    error_code = "GUARDIAN_PENDING_DELETION"


class DuplicateEmailChangeRequestError(AppException):
    status_code = 409
    detail = HTTP409.DUPLICATE_EMAIL_CHANGE_REQUEST
    error_code = "DUPLICATE_EMAIL_CHANGE_REQUEST"


def handle_username_integrity_error(error: IntegrityError) -> None:
    if "user_credentials_username_key" in str(error.orig):
        raise UsernameAlreadyTakenError()


def handle_non_student_unique_contact_error(error: IntegrityError) -> None:
    error_detail = str(error.orig)

    if "uix_non_student_unique_phone" in error_detail:
        raise DuplicatePhoneNumberError()

    if "uix_non_student_unique_email" in error_detail:
        raise DuplicateEmailError()

    if "uix_one_personal_account_per_identity" in error_detail:
        raise GuardianAccountAlreadyExistsError()
