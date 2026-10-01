from enum import StrEnum


class IdempotencyStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETE = "complete"


class IdempotencyOperation(StrEnum):
    USER_REGISTER = "user-register"
    GUARDIAN_LINK = "guardian-link"
    ADMIN_RESET_PASSWORD = "admin_reset_password"
    FORGOT_PASSWORD = "forgot-password"
