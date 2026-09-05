class HTTP400:
    ACTIVATION_TOKEN_USED = "Account already activated or was never invited"
    INVALID_ACTIVATION_TOKEN = "Invalid invite token"
    EXPIRED_ACTIVATION_TOKEN = "Expired invite token"
    INVALID_RESET_PASSWORD_TOKEN = "Invalid reset password token"
    EXPIRED_RESET_PASSWORD_TOKEN = "Expired reset password token"
    NO_CHANGES_DETECTED = "No changes detected"


class HTTP401:
    INVALID_ACCESS_TOKEN = "Invalid access token"
    EXPIRED_ACCESS_TOKEN = "Expired access token"
    INVALID_REFRESH_TOKEN = "Invalid refresh token"
    EXPIRED_REFRESH_TOKEN = "Expired refresh token"
    INVALID_TOKEN_TYPE = "Invalid token type"
    INVALID_CREDENTIALS = "Invalid credentials"


class HTTP403:
    ACCESS_DENIED = "Access denied"
    ACCOUNT_DEACTIVATED = "Your account has been deactivated"
    ACCOUNT_NOT_ACTIVATED = "Account has not been activated yet"
    ACCOUNT_INACTIVE = "Account is inactive"
    EXPIRED_DELETION_GRACE_PERIOD = "Account deletion grace period has expired"
    ACCOUNT_GRADUATED = "This account belongs to a graduated student"
    ACCOUNT_EXPELLED = "This account has been expelled"
    ACCOUNT_WITHDRAWN = "This account has been withdrawn"
