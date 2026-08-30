import time
import uuid

from fastapi.responses import JSONResponse
import sentry_sdk
import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Generates or propagates a request correlation ID.

    - Reads X-Request-ID from incoming headers; generates a UUID4 if absent.
    - Clears any previous contextvars state, then binds request_id and
      environment so all log events within this request carry them automatically.
    - Appends X-Request-ID to the response headers for client-side tracing.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        environment = getattr(request.app.state, "settings", None)
        env_name = environment.ENVIRONMENT if environment else "unknown"

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            environment=env_name,
        )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs method, path, status code, and duration for every request.

    duration_ms is measured with time.perf_counter() for sub-millisecond
    precision. The log event fires after the response is fully sent.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            "request_handled",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """
    Catches unhandled exceptions before they escape the middleware stack.

    BaseHTTPMiddleware with call_next re-raises exceptions instead of routing
    them to FastAPI exception handlers. This middleware catches them first
    and returns the correct 500 response.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)

        except Exception as exc:
            logger.exception(
                "unhandled_exception",
                path=request.url.path,
                method=request.method,
                exc_info=exc,
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
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response
