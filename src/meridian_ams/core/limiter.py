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

_STORAGE_OPTIONS = {
    "socket_connect_timeout": 1,
    "socket_timeout": 1,
}


def get_user_identifier(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")

    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ")

        try:
            payload = decode_access_token(token)
        except jwt.PyJWTError:
            return get_remote_address(request)

        user_id = payload.get("sub")
        if user_id:
            return f"user:{user_id}"

    return get_remote_address(request)


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,
    storage_options=_STORAGE_OPTIONS,
    headers_enabled=True,
    swallow_errors=False,
)


async def rate_limit_exceeded_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    logger.warning(
        "rate_limit_exceeded",
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=429,
        content={
            "error_code": "RATE_LIMIT_EXCEEDED",
            "detail": "Too many requests.",
        },
    )
