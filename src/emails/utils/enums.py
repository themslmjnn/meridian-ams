from enum import StrEnum


class EmailType(StrEnum):
    NEW_LOGIN = "new_login"
    ACCOUNT_ACTIVATION = "account_activation"
    ADMIN_PROFILE_OVERRIDE = "admin_profile_override"
    ADMIN_CREDENTIALS_OVERRIDE = "admin_credentials_override"
    ADMIN_ACCOUNT_DEACTIVATION = "admin_account_deactivation"
    ADMIN_ACCOUNT_ACTIVATION = "admin_account_activation"
    ADMIN_ACCOUNT_DELETION = "admin_account_deletion"
    ADMIN_ACCOUNT_DELETION_CANCELLATION = "admin_account_deletion_cancellation"
    ADMIN_PASSWORD_RESET = "admin_password_reset"
    PUBLIC_PASSWORD_RESET = "public_password_reset"
    EMAIL_CHANGE = "email_change"
    EMAIL_CHANGE_CONFIRMATION = "email_change_confirmation"
    PASSWORD_CHANGE_CONFIRMATION = "password_change_confirmation"


class EmailStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
