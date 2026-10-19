from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

logger = structlog.get_logger(__name__)


# Base application exception
class AppException(Exception):
    """Base class for expected application errors. Subclasses set the three fields."""

    status_code: int
    error_code: str
    detail: str

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail if detail is not None else type(self).detail
        super().__init__(self.detail)


# Global exception handlers
async def app_exception_handler(
    request: Request,
    exc: AppException,
) -> JSONResponse:
    """Handle expected application errors with a consistent JSON shape."""

    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code, "detail": exc.detail},
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """
    Normalise Pydantic v2 validation errors into a consistent 422 shape.

    The raw Pydantic error list is preserved under 'errors' so the client
    can map field-level failures without parsing the detail string.
    """

    errors = [
        {
            "field": " -> ".join(str(loc) for loc in err["loc"]),
            "message": err["msg"].removeprefix("Value error, "),
            "type": err["type"],
        }
        for err in exc.errors()
    ]

    return JSONResponse(
        status_code=422,
        content={
            "error_code": "VALIDATION_ERROR",
            "detail": "Request validation failed",
            "errors": errors,
        },
    )


async def redis_error_handler(
    request: Request,
    exc: RedisError,
) -> JSONResponse:
    """
    Handle Redis errors from critical operations.

    Critical Redis wrappers propagate RedisError — this handler converts them
    to 503 Service Unavailable. The error is logged but not sent to Sentry
    as routine infrastructure blips; persistent failures will alert via uptime monitoring.
    """

    logger.error(
        "redis_critical_failure",
        error=str(exc),
        path=request.url.path,
    )

    return JSONResponse(
        status_code=503,
        content={
            "error_code": "SERVICE_UNAVAILABLE",
            "detail": "Required service is temporarily unavailable",
        },
    )


# Registration helper
def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI app."""

    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RedisError, redis_error_handler)  # type: ignore[arg-type]
