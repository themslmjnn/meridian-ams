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
    default_limits=["60/minute"],
)

user_limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri=settings.REDIS_URL,
    default_limits=["120/minute"],
)

limiter = ip_limiter
limiter.logger = logging.getLogger("slowapi")


async def rate_limit_exceeded_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    """
    Return 429 with a Retry-After header when the rate limit is exceeded.

    The Retry-After value is extracted from the exception when available.
    """
    retry_after = getattr(exc, "retry_after", None)

    logger.warning(
        "rate_limit_exceeded",
        path=request.url.path,
        method=request.method,
        retry_after=retry_after,
    )

    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)

    return JSONResponse(
        status_code=429,
        content={
            "error_code": "RATE_LIMIT_EXCEEDED",
            "detail": "Too many requests",
        },
        headers=headers,
    )
