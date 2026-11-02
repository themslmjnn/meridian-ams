from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from sqlalchemy import text

from meridian_ams.core.config import Settings, get_settings
from meridian_ams.core.logging import configure_logging
from meridian_ams.database.connection import build_engine, build_session_factory

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    Own the lifetime of shared resources.

    Startup:
    1. Read settings from app.state (attached by create_app)
    2. Build the DB engine (no connection is opened yet)
    3. Verify PostgreSQL is reachable. It is mandatory, so a failure
       here aborts startup.
    4. Attach the engine and session factory to app.state

    Shutdown:
    1. Dispose the DB engine. This runs in `finally`, so it also runs
       when the startup check fails.

    Logs `database_connected` after the startup check and
    `database_disposed` after shutdown.
    """

    settings: Settings = app.state.settings

    logger.info("application_starting", environment=settings.ENVIRONMENT)

    engine = build_engine(settings)

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        logger.info("database_connected")

        app.state.engine = engine
        app.state.session_factory = build_session_factory(engine)

        logger.info("application_ready")

        yield

    finally:
        logger.info("application_shutting_down")

        is_shutdown_completed = False

        try:
            await engine.dispose()

            logger.info("database_disposed")

            is_shutdown_completed = True

        except Exception:
            logger.exception("shutdown_step_failed", step="db_engine")

        if is_shutdown_completed:
            logger.info("application_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Build the application.

    1. Resolve settings once. Pass `settings` explicitly in tests;
       otherwise they come from get_settings().
    2. Configure logging, before anything else can log.
    3. Create the FastAPI app and attach settings to app.state.
    """

    settings = settings or get_settings()

    configure_logging(settings.LOG_LEVEL)

    app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

    app.state.settings = settings

    return app


app = create_app()
