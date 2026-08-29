class HTTP400:
    INVITE_TOKEN_USED = "Account already activated or was never invited"
    INVALID_INVITE_TOKEN = "Invalid invite token"
    EXPIRED_INVITE_TOKEN = "Expired invite token"
    NO_CHANGES_DETECTED = "No changes detected"
    EXPIRED_RESET_PASSWORD_TOKEN = "Expired reset password token"
    INVALID_RESET_PASSWORD_TOKEN = "Invalid reset password token"


class HTTP401:
    INVALID_CREDENTIALS = "Invalid credentials"
    ACCOUNT_NOT_ACTIVATED = "Account has not been activated yet"
    INVALID_REFRESH_TOKEN = "Invalid refresh token"
    EXPIRED_REFRESH_TOKEN = "Expired refresh token"
    INVALID_ACCESS_TOKEN = "Invalid access token"
    EXPIRED_ACCESS_TOKEN = "Expired access token"
    INVALID_TOKEN_TYPE = "Invalid token type"
    ACCOUNT_DELETION_EXPIRED = "Account deletion grace period has expired"


class HTTP403:
    ACCESS_DENIED = "Access denied"
    ACCOUNT_DEACTIVATED = "Your account has been deactivated"


class HTTP404:
    PENDING_EMAIL = "Pending email not found"
    SUBJECT = "Subject not found"
    GROUP = "Group not found"


class HTTP409:
    SUBJECT_CODE = "Subject with this code already exists"
    GROUP_NAME = "Group with this name and academic year already exists"
