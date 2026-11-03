from enum import StrEnum


class IdempotencyStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETE = "complete"


class IdempotencyOperation(StrEnum):
    REGISTER_USER = "register-user"
    ADMIN_RESET_PASSWORD = "admin_reset_password"
    RESEND_ACTIVATION_TOKEN = "resend_activation_token"
    GUARDIAN_LINK = "guardian-link"
    FORGOT_PASSWORD = "forgot-password"
    CREATE_GUARDIAN_LINK = "create_guardian_link"
