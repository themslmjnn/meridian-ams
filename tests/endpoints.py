class AuthEndpoints:
    LOGIN = "/api/v1/auth/login"
    LOGOUT = "/api/v1/auth/logout"
    REFRESH = "/api/v1/auth/refresh-token"
    PASSWORD_RESET = "/api/v1/auth/password-reset"
    ACTIVATION = "/api/v1/auth/activation"


class UserEndpoints:
    ME = "/api/v1/users/me"
    ADMIN_USERS = "/api/v1/admin/users"
