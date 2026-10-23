class HTTP400:
    INVALID_GUARDIAN_ACCOUNT = "Invalid guardian account"
    INVALID_STUDENT_ACCOUNT = "The provided account is not a student account"
    INVALID_STUDENT_STATUS = "The following student can not have links"


class HTTP404:
    GUARDIAN_NOT_FOUND = "Guardian not found"
    STUDENT_NOT_FOUND = "Student not found"


class HTTP409:
    GUARDIAN_ALREADY_LINKED = "This guardian is already linked to this student"
    GUARDIAN_TYPE_TAKEN = "This student already has a guardian of this type"
