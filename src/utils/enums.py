from enum import StrEnum


class IdempotencyStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETE = "complete"


class IdempotencyOperation(StrEnum):
    USER_REGISTER = "user-register"
    GUARDIAN_LINK = "guardian-link"
    FORGOT_PASSWORD = "forgot-password"
