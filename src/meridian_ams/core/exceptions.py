from __future__ import annotations

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)


class AppException(Exception):
    """
    Base class for expected application errors.

    Subclasses override the class attributes. `detail` can also be overridden
    per raise: UserNotFoundError("No user with id 5").
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"
    detail: str = "Internal server error"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail

        super().__init__(self.detail)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Return expected application errors in the standard error shape."""

    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code, "detail": exc.detail},
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Give framework errors (404 unknown route, 405, ...) the standard shape."""

    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": "HTTP_ERROR", "detail": str(exc.detail)},
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Normalise Pydantic v2 validation errors into one 422 shape.

    Each entry has `field`, `message` and `type`. Pydantic's `ctx` and `input`
    are left out on purpose: they can hold values that are not JSON-serializable
    or that should not be echoed back.
    """

    errors = [
        {
            "field": " -> ".join(str(loc) for loc in error["loc"]),
            "message": error["msg"].removeprefix("Value error, "),
            "type": error["type"],
        }
        for error in exc.errors()
    ]

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error_code": "VALIDATION_ERROR",
            "detail": "Request validation failed",
            "errors": errors,
        },
    )


async def redis_error_handler(request: Request, exc: RedisError) -> JSONResponse:
    """
    Convert RedisError from critical operations into 503.

    Optional cache wrappers swallow RedisError; only critical paths reach here.
    """

    logger.error(
        "redis_critical_failure",
        error=repr(exc),
        path=request.url.path,
    )

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error_code": "SERVICE_UNAVAILABLE",
            "detail": "Required service is temporarily unavailable",
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort: log everything, tell the client nothing about internals."""

    logger.error(
        "unhandled_exception",
        method=request.method,
        path=request.url.path,
        exc_info=exc,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error_code": "INTERNAL_ERROR", "detail": "Internal server error"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI app."""

    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RedisError, redis_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
