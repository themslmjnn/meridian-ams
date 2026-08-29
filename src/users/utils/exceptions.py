from src.core.exceptions import AppException


class MaxStudentsPerPhoneNumberError(AppException):
    status_code = 409

class PhoneNumberAlreadyExistsError(AppException):
    status_code = 409

class MaxStudentsPerEmailError(AppException):
    status_code = 409