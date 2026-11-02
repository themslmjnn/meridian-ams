from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from meridian_ams.core.config import Settings, get_settings
from meridian_ams.database.connection import build_engine, build_session_factory


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
    """

    settings: Settings = app.state.settings

    engine = build_engine(settings)

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        app.state.engine = engine
        app.state.session_factory = build_session_factory(engine)

        yield

    finally:
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Build the application.

    Settings are resolved here, once. Pass `settings` explicitly in tests;
    otherwise they come from get_settings().
    """

    settings = settings or get_settings()

    app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

    app.state.settings = settings

    return app


app = create_app()
