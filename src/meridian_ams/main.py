import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from sqlalchemy import text

from meridian_ams.api.health import router as health_router
from meridian_ams.core.config import Settings, get_settings
from meridian_ams.core.exceptions import register_exception_handlers
from meridian_ams.core.logging import configure_logging
from meridian_ams.core.redis.client import build_redis
from meridian_ams.database.connection import build_engine, build_session_factory
from meridian_ams.workers.email_worker import run_email_worker

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    Own the lifetime of shared resources.

    Startup:
    1. Read settings from app.state (attached by create_app)
    2. Build the DB engine and the Redis client (neither connects yet)
    3. Verify PostgreSQL is reachable
    4. Verify Redis is reachable
       Both are mandatory, so a failure in either aborts startup.
    5. Attach the engine, session factory and Redis client to app.state

    Shutdown (reverse of startup), one guarded step at a time:
    1. Close the Redis client
    2. Dispose the DB engine
       A failing step is logged and does not skip the next one. Shutdown
       runs in `finally`, so it also runs after a failed startup, and the
       resources built in step 2 are released even if nothing was attached.

    Logs: `application_starting`, `postgresql_connected`, `redis_connected`,
    `application_ready`, `application_shutting_down`, `redis_closed`,
    `db_engine_disposed`, `shutdown_step_failed` (per failing step), and
    `application_stopped` only if every shutdown step succeeded.
    """

    settings: Settings = app.state.settings

    logger.info("application_starting", environment=settings.ENVIRONMENT)

    engine = build_engine(settings)
    redis = build_redis(settings)

    tasks: list[asyncio.Task[None]] = []

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        logger.info("postgresql_connected")

        await redis.ping()

        logger.info("redis_connected")

        app.state.engine = engine
        app.state.async_session_factory = build_session_factory(engine)
        app.state.redis = redis

        tasks.append(
            asyncio.create_task(
                run_email_worker(engine=app.state.engine), name="email_worker"
            )
        )

        logger.info("workers_started")
        logger.info("application_ready")

        yield

    finally:
        logger.info("application_shutting_down")

        is_shutdown_completed = True

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
                    error=repr(result),
                    error_type=type(result).__name__,
                )

        shutdown = (
            ("redis", redis.aclose, "redis_closed"),
            ("db_engine", engine.dispose, "db_engine_disposed"),
        )

        for step, close, log in shutdown:
            try:
                await close()

                logger.info(log)

            except Exception:
                is_shutdown_completed = False

                logger.exception("shutdown_step_failed", step=step)

        if is_shutdown_completed:
            logger.info("application_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Build the application.

    1. Resolve settings once. Pass `settings` explicitly in tests;
       otherwise they come from get_settings().
    2. Configure logging, before anything else can log.
    3. Create the FastAPI app and attach settings to app.state.
    4. Register exception handlers, so every error leaves the app in the
       standard shape.
    5. Register routers.

    Resources (database, Redis) are not created here. The lifespan builds
    them, so tests that skip the lifespan must set them on app.state.
    """

    settings = settings or get_settings()

    configure_logging(settings.LOG_LEVEL)

    app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

    app.state.settings = settings

    # Exceptions
    register_exception_handlers(app)

    # Routers
    app.include_router(health_router)

    return app


app = create_app()
