from src.users.utils.enums import UserRole

STUDENT_MIN_AGE = 6
STUDENT_MAX_AGE = 21

STAFF_AND_GUARDIAN_MAX_SHARED_CONTACT = 1
STUDENT_MAX_SHARED_CONTACT = 3
SYSTEM_ADMIN_INVISIBLE_ROLES = frozenset({UserRole.SYSTEM_ADMIN})


class HTTP400:
    USER_TYPE_MISMATCH = (
        "Submitted update payload type does not match the target user's role"
    )


class HTTP404:
    IDENTITY = "Identity not found"
    CREDENTIALS = "Credentials not found"


class HTTP409:
    DUPLICATE_USERNAME = "Username already taken"
    DUPLICATE_PHONE_NUMBER = "Phone number already taken"
    DUPLICATE_EMAIL = "Email already taken"
    MAX_STUDENTS_PER_PHONE_NUMBER = (
        "Maximum number of students with this phone number reached"
    )
    MAX_STUDENTS_PER_EMAIL = "Maximum number of students with this email reached"
    DUPLICATE_GUARDIAN_ACCOUNT = "Guardian account already exists"
