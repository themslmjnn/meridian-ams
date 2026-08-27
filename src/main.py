from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # type: ignore[attr-defined]
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.api.health import router as health_router
from src.core.caching import close_redis, init_redis
from src.core.config import get_settings
from src.core.exceptions import AppException, register_exception_handlers
from src.core.logging import configure_logging
from src.core.middleware import (
    CorrelationIDMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from src.database.connection import dispose_engine

logger = structlog.get_logger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage startup and shutdown of shared resources.

    Startup order:
    1. Configure logging (must be first — all subsequent startup logs use it)
    2. Attach settings to app.state (middleware and health checks read from here)
    3. Initialise Redis and verify connectivity
    4. Initialise Sentry (if DSN configured)
    5. Initialise Prometheus (if enabled)
    6. Workers are started in Phase 13 — stubs only until then

    Shutdown order (reverse of startup):
    1. Cancel and await worker tasks
    2. Close Redis connection
    3. Dispose SQLAlchemy engine connection pool
    """
    # --- Startup ---
    configure_logging(settings.ENVIRONMENT)
    app.state.settings = settings

    logger.info("application_starting", environment=settings.ENVIRONMENT)

    await init_redis(app)
    _init_sentry()
    _init_prometheus(app)

    logger.info("application_ready")

    yield

    # --- Shutdown ---
    logger.info("application_shutting_down")

    await close_redis(app)
    await dispose_engine()

    logger.info("application_stopped")


def _init_sentry() -> None:
    if not settings.SENTRY_DSN:
        return

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
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
    if not settings.METRICS_ENABLED:
        return

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
    logger.info("prometheus_initialised")


def create_app() -> FastAPI:
    is_production_like = settings.ENVIRONMENT in ("staging", "production")

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url=None if is_production_like else "/docs",
        redoc_url=None if is_production_like else "/redoc",
        openapi_url=None if is_production_like else "/openapi.json",
        lifespan=lifespan,
    )

    # -------------------------------------------------------------------------
    # Middleware — registration order is REVERSE of execution order.
    # Starlette applies middleware bottom-up (last added = outermost wrapper).
    #
    # Execution order (first to last):
    #   1. CorrelationIDMiddleware   — sets request_id, clears contextvars
    #   2. RequestLoggingMiddleware  — logs method/path/status/duration
    #   3. SecurityHeadersMiddleware — appends security headers
    #   4. TrustedHostMiddleware     — validates Host header (prod/staging only)
    #   5. CORSMiddleware            — handles preflight and CORS headers
    #   6. SlowAPIMiddleware         — rate limiting
    # -------------------------------------------------------------------------

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if is_production_like:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.ALLOWED_HOSTS,
        )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)

    # Exception handlers
    register_exception_handlers(app)

    # Routers
    app.include_router(health_router)

    return app


app = create_app()
