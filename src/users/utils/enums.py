from enum import StrEnum


class UserRole(StrEnum):
    SYSTEM_ADMIN = "system_admin"
    DIRECTOR = "director"
    TEACHER = "teacher"
    STUDENT = "student"
    GUARDIAN = "guardian"


class UserStatus(StrEnum):
    ACTIVE = "active"
    PENDING_ACTIVATION = "pending_activation"
    DEACTIVATED = "deactivated"
    DELETED = "deleted"
    PENDING_DELETION = "pending_deletion"
    GRADUATED = "graduated"
    WITHDRAWN = "withdrawn"
    EXPELLED = "expelled"


class AccountType(StrEnum):
    STUDENT = "student"
    WORK = "work"
    PERSONAL = "personal"
