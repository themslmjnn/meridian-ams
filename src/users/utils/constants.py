STUDENT_MIN_AGE = 6
STUDENT_MAX_AGE = 21

STAFF_AND_GUARDIAN_MAX_SHARED_CONTACT = 1
STUDENT_MAX_SHARED_CONTACT = 3


class HTTP409:
    USERNAME = "Username already taken."
    DUPLICATE_PHONE_NUMBER = "An account with this phone number already exists."
    DUPLICATE_EMAIL = "An account with this email already exists."
    MAX_STUDENTS_PER_PHONE = (
        "Maximum number of students with this phone number reached."
    )
    MAX_STUDENTS_PER_EMAIL = "Maximum number of students with this email reached."
