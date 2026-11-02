from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from meridian_ams.core.config import get_settings
from meridian_ams.database.connection import build_engine, build_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    Manage startup and shutdown of shared resources.

    Startup order:
    1. Attach settings to app.state
    2. Build the DB engine and Redis client (neither connects yet)
    3. Verify PostgreSQL is reachable. PostgreSQL is mandatory, so a
       failure here aborts startup.
    4. Attach engine and session factory to app.state

    Shutdown (always runs, even after a partial startup failure):
    1. Dispose the DB engine (reverse of startup).
       Each step is guarded so one failure doesn't skip the rest.
    """

    settings = get_settings()

    app.state.settings = settings

    engine = build_engine(settings)

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        app.state.engine = engine
        app.state.session_factory = build_session_factory(engine)

        yield

    finally:
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

    return app


app = create_app()
