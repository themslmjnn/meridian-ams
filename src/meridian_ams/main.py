import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from meridian_ams.api.health import router as health_router
from meridian_ams.auth.routers import router as auth_router
from meridian_ams.core.config import Settings, get_settings
from meridian_ams.core.exceptions import register_exception_handlers
from meridian_ams.core.logging import configure_logging
from meridian_ams.core.redis.client import build_redis
from meridian_ams.database.connection import build_engine, build_session_factory
from meridian_ams.users.routers import router as users_routers
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
    6. Start the background workers (email worker) as asyncio tasks

    Shutdown (reverse of startup):
    1. Cancel the workers and wait for them. A worker that ended with an
       error is logged.
    2. Close the Redis client
    3. Dispose the DB engine
       A failing step is logged and does not skip the next one. Shutdown
       runs in `finally`, so it also runs after a failed startup, and the
       resources built in step 2 are released even if nothing was attached.
    """

    settings: Settings = app.state.settings

    logger.info("application_starting", environment=settings.ENVIRONMENT)

    engine: AsyncEngine = build_engine(settings)
    redis: Redis = build_redis(settings)

    tasks: list[asyncio.Task[None]] = []

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        logger.info("postgresql_connected")

        await redis.ping()

        logger.info("redis_connected")

        app.state.engine = engine
        app.state.session_factory = build_session_factory(engine)
        app.state.redis = redis

        tasks.append(
            asyncio.create_task(
                run_email_worker(
                    session_factory=app.state.session_factory, settings=settings
                ),
                name="email_worker",
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
                is_shutdown_completed = False

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
    4. Register middleware. Starlette treats the LAST one added as the
       outermost, so they are added in reverse of execution order.
       Request path, outermost to innermost:
         CorrelationID -> RequestLogging -> SecurityHeaders -> CORS
         -> ExceptionHandler -> routes
       ExceptionHandler sits innermost so its 500/503 responses still get
       CORS headers, security headers and a request ID, and so
       RequestLogging sees the real status code.
    5. Register exception handlers, so every error leaves the app in the
       standard shape.
    6. Register routers.

    Resources (database, Redis) are not created here. The lifespan builds
    them, so tests that skip the lifespan must set them on app.state.
    """

    settings = settings or get_settings()

    configure_logging(
        log_level=settings.LOG_LEVEL,
        json_logs=settings.ENVIRONMENT == "production",
        environment=settings.ENVIRONMENT,
    )

    app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

    app.state.settings = settings

    # Exceptions
    register_exception_handlers(app)

    # Routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_routers)

    return app


app = create_app()
