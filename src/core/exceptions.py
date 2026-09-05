import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

logger = structlog.get_logger(__name__)


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

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or getattr(self, "detail", "An error occurred.")
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
            "message": err["msg"],
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
    as routine infrastructure blips; persistent failures will alert via
    uptime monitoring.
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
def register_exception_handlers(app: "object") -> None:
    """
    Register all global exception handlers on the FastAPI app.

    Import order matters: more specific exceptions must be registered before
    broader ones so FastAPI matches the most specific handler first.
    """
    assert isinstance(app, FastAPI)

    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RedisError, redis_error_handler)  # type: ignore[arg-type]
