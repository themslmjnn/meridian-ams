import logging

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.core.config import get_settings

logger = structlog.get_logger(__name__)

settings = get_settings()

# Bound blocking Redis I/O: slowapi's storage is synchronous.
_STORAGE_OPTIONS = {"socket_connect_timeout": 1, "socket_timeout": 1}


def get_user_identifier(request: Request) -> str:
    """
    Extract a rate limit key from the request.

    For authenticated requests: keys by the user's public UUID from the JWT
    payload. This gives accurate per-user rate limiting regardless of IP —
    important for users behind corporate NATs or shared VPNs.

    For unauthenticated requests (no token or invalid token): falls back to
    the client IP address so the limiter never crashes on missing auth.
    """

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer ") :]
        try:
            # Import here to avoid circular import at module load time
            from src.core.security import decode_access_token

            payload = decode_access_token(token)
            user_id = payload.get("sub")

            if user_id:
                return f"user:{user_id}"

        except Exception:
            # Expired, tampered, or otherwise invalid token —
            # fall through to IP-based limiting
            pass

    return get_remote_address(request)


ip_limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,
    storage_options=_STORAGE_OPTIONS,
    default_limits=[settings.RATE_LIMIT_DEFAULT_IP],
    headers_enabled=True,
)

# Applies only to routes decorated with @user_limiter.limit(...);
# SlowAPIMiddleware uses app.state.limiter (ip_limiter) for default limits.
user_limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri=settings.REDIS_URL,
    storage_options=_STORAGE_OPTIONS,
    headers_enabled=True,
)

limiter = ip_limiter
limiter.logger = logging.getLogger("slowapi")


async def rate_limit_exceeded_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    """Return 429 with Retry-After (and X-RateLimit-*) headers."""

    response = JSONResponse(
        status_code=429,
        content={
            "error_code": "RATE_LIMIT_EXCEEDED",
            "detail": "Too many requests",
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
