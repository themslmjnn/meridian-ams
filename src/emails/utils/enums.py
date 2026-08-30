from enum import StrEnum


class EmailType(StrEnum):
    ACTIVATION = "activation"
    UPDATING_ACCOUNT = "updating_account"
    ADMIN_CREDENTIALS_OVERRIDE = "admin_credentials_override"
    ACCOUNT_DEACTIVATION = "account_deactivation"
    ACCOUNT_ACTIVATION = "account_activation"
    PASSWORD_RESET_ADMIN = "password_reset_admin"
    EMAIL_CHANGE_CODE = "email_change_code"
    EMAIL_CHANGED = "email_changed"
    PASSWORD_CHANGED = "password_changed"
    FORGOT_PASSWORD = "forgot_password"


class EmailStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
