from meridian_ams.core.exceptions import AppException


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
