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
    detail = "Username already taken"
    error_code = "USERNAME_ALREADY_TAKEN"


class DuplicatePhoneNumberError(AppException):
    status_code = 409
    detail = "Phone number already taken"
    error_code = "DUPLICATE_PHONE"


class DuplicateEmailError(AppException):
    status_code = 409
    detail = "Email already taken"
    error_code = "DUPLICATE_EMAIL"


class MaxStudentsPerPhoneNumberError(AppException):
    status_code = 409
    detail = "Maximum number of students with this phone number reached"
    error_code = "MAX_STUDENTS_PER_PHONE_NUMBER"


class MaxStudentsPerEmailError(AppException):
    status_code = 409
    detail = "Maximum number of students with this email reached"
    error_code = "MAX_STUDENTS_PER_EMAIL"


class CredentialsAlreadyExistsError(AppException):
    status_code = 409
    detail = "Credentials already exists"
    error_code = "CREDENTIALS_ALREADY_EXISTS"


# HTTP422
class StudentNotEligibleForAdditionalAccountError(AppException):
    status_code = 422
    detail = "Only graduated students can be given an additional account"
    error_code = "STUDENT_NOT_ELIGIBLE_FOR_ADDITIONAL_ACCOUNT"


class IdentityBelowMinimumAgeError(AppException):
    status_code = 422
    detail = "Identity does not meet the minimum age for this account"
    error_code = "IDENTITY_BELOW_MINIMUM_AGE"


def handle_username_integrity_error(error: IntegrityError) -> None:
    if "uq_user_credentials_username" in str(error.orig):
        raise UsernameAlreadyTakenError()


def handle_non_student_unique_email_error(error: IntegrityError) -> None:
    if "uix_non_student_unique_email" in str(error.orig):
        raise DuplicateEmailError()


def handle_account_per_identity_error(error: IntegrityError) -> None:
    if "uq_user_credentials_identity_id_account_type" in str(error.orig):
        raise CredentialsAlreadyExistsError()
