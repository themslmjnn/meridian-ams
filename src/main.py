import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware  # type: ignore[attr-defined]
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.api.health import router as health_router
from src.auth.routers import router as auth_router
from src.core.caching import close_redis, init_redis
from src.core.config import get_settings
from src.core.exceptions import AppException, register_exception_handlers
from src.core.idempotency import _CachedResponseSignal, make_cached_response
from src.core.limiter import limiter, rate_limit_exceeded_handler
from src.core.logging import configure_logging
from src.core.middleware import (
    CorrelationIDMiddleware,
    ExceptionHandlerMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from src.database.connection import dispose_engine
from src.users.routers.director import router as users_director_router
from src.users.routers.guardian import router as users_guardian_router
from src.users.routers.shared import router as users_shared_router
from src.users.routers.system_admin import router as users_system_admin_router
from src.utils.email import close_email_client
from src.workers.deletion_worker import run_deletion_worker
from src.workers.email_worker import run_email_worker

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage startup and shutdown of shared resources.

    Startup order:
    1. Configure logging (first — all subsequent startup logs use it)
    2. Attach settings to app.state
    3. Initialise Sentry (before anything that can fail)
    4. Initialise Redis and verify connectivity
    5. Start email and deletion worker tasks

    Prometheus is initialised in create_app(), because it adds middleware
    and that is not allowed once the app has started.

    Shutdown (always runs, even after a partial startup failure):
    1. Cancel and await worker tasks
    2. Close email client, Redis, and the DB engine (each step guarded)
    """

    # --- Startup ---
    settings = get_settings()

    configure_logging(
        settings.IS_PRODUCTION_LIKE, settings.ENVIRONMENT, settings.LOG_LEVEL
    )
    app.state.settings = settings

    _init_sentry()  # before anything that can fail, so startup errors are captured

    logger.info("application_starting", environment=settings.ENVIRONMENT)

    tasks: list[asyncio.Task[None]] = []

    try:
        await init_redis(app)

        tasks.append(asyncio.create_task(run_email_worker(), name="email_worker"))
        tasks.append(asyncio.create_task(run_deletion_worker(), name="deletion_worker"))
        logger.info("workers_started")

        logger.info("application_ready")

        yield

    finally:
        # --- Shutdown ---

        logger.info("application_shutting_down")

        for task in tasks:
            task.cancel()

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for task, result in zip(tasks, results, strict=True):
            if isinstance(result, BaseException) and not isinstance(
                result, asyncio.CancelledError
            ):
                logger.error(
                    "worker_shutdown_error",
                    worker=task.get_name(),
                    error=str(result),
                    error_type=type(result).__name__,
                )

        # Each step is guarded so one failure doesn't skip the rest.
        for step, close in (
            ("email_client", close_email_client),
            ("redis", lambda: close_redis(app)),
            ("db_engine", dispose_engine),
        ):
            try:
                await close()

            except Exception:
                logger.exception("shutdown_step_failed", step=step)

        logger.info("application_stopped")


def _init_sentry() -> None:
    settings = get_settings()
    if not settings.SENTRY_DSN:
        return

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        ignore_errors=[AppException],
        traces_sample_rate=0.1,
        before_send=_sentry_before_send,
    )

    logger.info("sentry_initialised")


def _sentry_before_send(
    event: dict,  # type: ignore[type-arg]
    hint: dict,  # type: ignore[type-arg]
) -> dict | None:  # type: ignore[type-arg]
    """Filter additional noise before events reach Sentry."""

    return event


def _init_prometheus(app: FastAPI) -> None:
    if not get_settings().METRICS_ENABLED:
        return

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    logger.info("prometheus_initialised")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url=None if settings.IS_PRODUCTION_LIKE else "/docs",
        redoc_url=None if settings.IS_PRODUCTION_LIKE else "/redoc",
        openapi_url=None if settings.IS_PRODUCTION_LIKE else "/openapi.json",
        lifespan=lifespan,
    )

    app.state.limiter = limiter

    # -------------------------------------------------------------------------
    # Middleware — registration order is REVERSE of execution order.
    # Starlette applies middleware bottom-up (last added = outermost wrapper).

    # Execution order (first to last):
    #   1. CorrelationIDMiddleware    — sets request_id, clears contextvars
    #   2. RequestLoggingMiddleware   — logs method/path/status/duration
    #   3. SecurityHeadersMiddleware  — appends security headers
    #   4. TrustedHostMiddleware      — validates Host header (prod/staging only)
    #   5. CORSMiddleware             — handles preflight and CORS headers
    #   6. ExceptionHandlerMiddleware — turns unhandled errors into a JSON 500
    #   7. SlowAPIMiddleware          — rate limiting
    # -------------------------------------------------------------------------

    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(ExceptionHandlerMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if settings.IS_PRODUCTION_LIKE:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.ALLOWED_HOSTS,
        )

    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.IS_PRODUCTION_LIKE)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)

    _init_prometheus(app)

    # Exception handlers
    register_exception_handlers(app)

    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    @app.exception_handler(_CachedResponseSignal)
    async def cached_response_handler(request: Request, exc: _CachedResponseSignal):
        return make_cached_response(exc)

    # Routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_system_admin_router)
    app.include_router(users_director_router)
    app.include_router(users_guardian_router)
    app.include_router(users_shared_router)

    return app


app = create_app()
