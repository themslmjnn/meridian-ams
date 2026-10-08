from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

logger = structlog.get_logger(__name__)

_FIELDS = ("status_code", "error_code", "detail")


# Base application exception
class AppException(Exception):
    """
    Base class for all expected application errors.

    Subclass this for domain-specific errors (e.g. UserNotFoundError).
    Instances are caught by app_exception_handler and returned as structured
    JSON. They are NOT forwarded to Sentry — expected errors are noise there.
    """

    status_code: int
    detail: str
    error_code: str

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

        status_code = getattr(cls, "status_code", None)
        if (
            not isinstance(status_code, int)
            or isinstance(status_code, bool)
            or not 400 <= status_code <= 599
        ):
            raise TypeError(f"{cls.__name__}.status_code must be an int in 400-599")

        for attr in ("error_code", "detail"):
            value = getattr(cls, attr, None)
            if not isinstance(value, str) or not value:
                raise TypeError(
                    f"{cls.__name__}.{attr} must be a non-empty str class attribute. "
                    f"Example:\n"
                    f"    class {cls.__name__}(AppException):\n"
                    f"        status_code = 404\n"
                    f"        error_code = 'RESOURCE_NOT_FOUND'\n"
                    f"        detail = 'The requested resource was not found.'"
                )

        extra = [
            name
            for name, value in vars(cls).items()
            if not name.startswith("_") and name not in _FIELDS and not callable(value)
        ]

        if extra:
            raise TypeError(
                f"{cls.__name__} defines unsupported attributes {extra}; "
                f"only {list(_FIELDS)} are allowed."
            )

    def __init__(self, detail: str | None = None) -> None:
        if type(self) is AppException:
            raise TypeError(
                "AppException must not be raised directly. "
                "Define a subclass with status_code, error_code, and detail."
            )

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
