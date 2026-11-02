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
    INACTIVE = "inactive"
    GRADUATED = "graduated"
    WITHDRAWN = "withdrawn"
    EXPELLED = "expelled"


class AccountType(StrEnum):
    STUDENT = "student"
    WORK = "work"
    PERSONAL = "personal"
