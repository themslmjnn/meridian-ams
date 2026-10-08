import re
import time
import uuid

import sentry_sdk
import structlog
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.core.exceptions import redis_error_handler

logger = structlog.get_logger(__name__)

_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")


def _resolve_request_id(raw: str | None) -> str:
    """Accept a client-supplied ID only if it is short and boring."""

    if raw and _REQUEST_ID_RE.fullmatch(raw):
        return raw

    return str(uuid.uuid4())


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Generates or propagates a request correlation ID.

    - Reads X-Request-ID from incoming headers; uses it only if it matches
      [A-Za-z0-9._-]{1,64}, otherwise generates a UUID4.
    - Binds request_id so all log events within this request carry it
      automatically. (environment is added by the logging processor.)
    - Appends X-Request-ID to the response headers for client-side tracing.
    - Clears the context when the request finishes.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = _resolve_request_id(request.headers.get("X-Request-ID"))

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id

            return response

        finally:
            structlog.contextvars.clear_contextvars()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs method, path, status code, and duration for every request.

    The event fires when the response headers are ready, so duration_ms does
    not include body streaming. Healthy health-probe requests log at debug.
    """

    @staticmethod
    def _log(request: Request, status_code: int, start: float) -> None:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        is_quiet = request.url.path.startswith("/health/") and status_code < 400
        log = logger.debug if is_quiet else logger.info

        log(
            "request_handled",
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=duration_ms,
        )

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()

        try:
            response = await call_next(request)

        except Exception:
            self._log(request, 500, start)

            raise

        self._log(request, response.status_code, start)

        return response


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """
    Convert unhandled exceptions into the standard JSON 500.

    Exceptions with a registered handler never reach this point. It sits inside
    the correlation, logging, security and CORS middleware so the 500 response
    still carries request_id, security headers and CORS headers.

    RedisError is handled here as a 503 because SlowAPIMiddleware (the
    critical-Redis rate limiter) runs outside FastAPI's exception handling.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)

        except RedisError as exc:
            return await redis_error_handler(request, exc)

        except Exception as exc:
            logger.exception(
                "unhandled_exception",
                path=request.url.path,
                method=request.method,
            )

            sentry_sdk.capture_exception(exc)

            return JSONResponse(
                status_code=500,
                content={
                    "error_code": "INTERNAL_SERVER_ERROR",
                    "detail": "An unexpected error occurred.",
                },
            )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Appends security-related response headers to every response.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - Referrer-Policy: strict-origin-when-cross-origin
    - Cache-Control: no-store (unless the handler set its own)
    - Strict-Transport-Security (only when hsts=True, i.e. staging/production)
    """

    def __init__(self, app, *, hsts: bool = False) -> None:
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers.setdefault("Cache-Control", "no-store")

        if self.hsts:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"

        return response
