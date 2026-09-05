from src.users.utils.enums import UserRole

STUDENT_MIN_AGE = 6
STUDENT_MAX_AGE = 21

DELETION_GRACE_PERIOD_DAYS = 30

STAFF_AND_GUARDIAN_MAX_SHARED_CONTACT = 1
STUDENT_MAX_SHARED_CONTACT = 3

SYSTEM_ROLE = frozenset({UserRole.SYSTEM_ADMIN})
STAFF_ROLES = frozenset({UserRole.DIRECTOR, UserRole.TEACHER})
GUARDIAN_ROLE = frozenset({UserRole.GUARDIAN})
STUDENT_ROLE = frozenset({UserRole.STUDENT})
TEACHER_ROLE = frozenset({UserRole.TEACHER})


class HTTP400:
    UPDATE_PAYLOAD_MISMATCH = (
        "Submitted update payload type does not match the target user's role"
    )
    EXPIRED_EMAIL_CHANGE_CODE = "Email change code has expired"
    INVALID_EMAIL_CHANGE_CODE = "Invalid email change code"
    INCORRECT_PASSWORD = "Incorrect password"


class HTTP403:
    INVALID_STATUS_TRANSITION = "Invalid status transition"


class HTTP404:
    IDENTITY = "Identity not found"
    CREDENTIALS = "Credentials not found"
    USER = "User not found"
    NO_PENDING_EMAIL_CHANGE = "No email change is currently pending"


class HTTP409:
    DUPLICATE_USERNAME = "Username already taken"
    DUPLICATE_PHONE_NUMBER = "Phone number already taken"
    DUPLICATE_EMAIL = "Email already taken"
    MAX_STUDENTS_PER_PHONE_NUMBER = (
        "Maximum number of students with this phone number reached"
    )
    MAX_STUDENTS_PER_EMAIL = "Maximum number of students with this email reached"
    DUPLICATE_GUARDIAN_ACCOUNT = "Guardian account already exists"
    USER_ALREADY_ACTIVE = "User is already active"
    USER_ALREADY_INACTIVE = "User is already inactive"
    USER_NOT_PENDING_ACTIVATION = "User is not pending activation"
    GUARDIAN_PENDING_DELETION = "This account is already pending deletion"
    DUPLICATE_EMAIL_CHANGE_REQUEST = (
        "An identical email change request is already pending"
    )
