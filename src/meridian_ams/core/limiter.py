import jwt
import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from meridian_ams.auth.tokens import decode_access_token
from meridian_ams.core.config import get_settings

logger = structlog.get_logger(__name__)

settings = get_settings()

# slowapi's Redis storage is synchronous, so bound how long it can block.
_STORAGE_OPTIONS = {"socket_connect_timeout": 1, "socket_timeout": 1}


def get_user_identifier(request: Request) -> str:
    """
    Rate limit key for authenticated routes.

    A valid Bearer token -> "user:<public_id>" (accurate per user, even
    behind a shared NAT). Missing or invalid token -> client IP, so the
    limiter never fails on bad auth; the auth dependency rejects it later.
    """

    auth_header = request.headers.get("Authorization", "")

    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer ") :]

        try:
            payload = decode_access_token(token)
        except jwt.PyJWTError:
            return get_remote_address(request)

        user_id = payload.get("sub")

        if user_id:
            return f"user:{user_id}"

    return get_remote_address(request)


# Unauthenticated routes (login, refresh, activation, forgot-password).
ip_limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,
    storage_options=_STORAGE_OPTIONS,
    headers_enabled=True,
    swallow_errors=False,  # Redis down -> error -> 503, never "unlimited"
)

# Authenticated routes (e.g. email-confirmation).
user_limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri=settings.REDIS_URL,
    storage_options=_STORAGE_OPTIONS,
    headers_enabled=True,
    swallow_errors=False,
)


async def rate_limit_exceeded_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    """Return the standard error shape as a 429 with Retry-After."""

    response = JSONResponse(
        status_code=429,
        content={
            "error_code": "RATE_LIMIT_EXCEEDED",
            "detail": "Too many requests.",
        },
    )

    view_limit = getattr(request.state, "view_rate_limit", None)

    if view_limit is not None:
        response = request.app.state.limiter._inject_headers(response, view_limit)

    logger.warning(
        "rate_limit_exceeded",
        path=request.url.path,
        method=request.method,
        retry_after=response.headers.get("Retry-After"),
    )

    return response
