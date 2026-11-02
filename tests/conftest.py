"""
Shared test fixtures.

Safety model: the suite drops and rebuilds the database schema and flushes a
Redis database, so everything destructive sits behind _guard_test_environment
and a second check on the database actually connected. Configuration comes
from pytest.ini (pytest-env sets ENVIRONMENT=test), which makes Settings load
.env.test.

The lifespan never runs in tests (ASGITransport skips it), so the `app`
fixture attaches the resources the lifespan would build. Background workers
are started by the lifespan, so they do not exist in tests: test their sweep
functions directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from meridian_ams.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]
TEST_REDIS_DB = 1


class UnsafeDatabaseError(RuntimeError):
    """Raised when a destructive step would run against a non-test database."""


def _alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    # env.py skips fileConfig() when this is False: fileConfig would otherwise
    # silence application logging for the rest of the session.
    config.attributes["configure_logger"] = False

    return config


async def _reset_schema(url: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool)

    try:
        async with engine.begin() as conn:
            current = await conn.scalar(text("SELECT current_database()"))

            if not (current or "").lower().endswith("_test"):
                raise UnsafeDatabaseError(
                    f"Refusing to reset database '{current}': name must end with '_test'"
                )

            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))

    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def settings() -> Settings:
    from meridian_ams.core.config import get_settings

    return get_settings()


@pytest.fixture(scope="session", autouse=True)
def _guard_test_environment(settings: Settings) -> None:
    problems: list[str] = []

    if settings.ENVIRONMENT != "test":
        problems.append(f"ENVIRONMENT is '{settings.ENVIRONMENT}', expected 'test'")

    if not settings.DB_NAME.lower().endswith("_test"):
        problems.append(f"DB_NAME '{settings.DB_NAME}' must end with '_test'")

    if settings.REDIS_DB != TEST_REDIS_DB:
        problems.append(f"REDIS_DB is {settings.REDIS_DB}, expected {TEST_REDIS_DB}")

    if problems:
        pytest.exit("Refusing to run tests: " + "; ".join(problems), returncode=2)


@pytest.fixture(scope="session")  # not autouse: only DB-backed tests pay for it
def migrated_database(settings: Settings, _guard_test_environment: None) -> None:
    """
    Rebuild the schema from the real migrations, never from metadata.create_all().

    ADR-0002 puts the updated_at triggers in migrations, so create_all() would
    produce a schema that differs from production. This fixture is synchronous
    on purpose: Alembic's async env.py calls asyncio.run(), which cannot run
    inside an already running event loop.
    """

    try:
        asyncio.run(_reset_schema(settings.DATABASE_URL))

    except UnsafeDatabaseError as exc:
        pytest.exit(str(exc), returncode=2)

    command.upgrade(_alembic_config(), "head")


@pytest_asyncio.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    # build_engine uses NullPool when ENVIRONMENT == "test": asyncpg connections
    # belong to the event loop that opened them, and every test has its own loop.
    # The engine is lazy, so requesting it does not touch the database.
    from meridian_ams.database.connection import build_engine

    engine = build_engine(settings)

    try:
        yield engine

    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_test_session(
    engine: AsyncEngine, migrated_database: None
) -> AsyncIterator[AsyncSession]:
    """
    A session inside an outer transaction that is rolled back after the test.

    Built from the production session factory, so options match production
    (autoflush=False: flush explicitly before querying for new rows).
    session.commit() only releases a savepoint, so tests can exercise commit
    paths without leaving data behind. Consequence: now() is frozen at the
    start of the test's transaction, so created_at and updated_at never differ
    inside one test. Tests of the updated_at trigger's timing need real commits.
    """

    from meridian_ams.database.connection import build_session_factory

    factory = build_session_factory(engine)

    async with engine.connect() as conn:
        outer = await conn.begin()
        session = factory(bind=conn, join_transaction_mode="create_savepoint")

        try:
            yield session

        finally:
            await session.close()
            await outer.rollback()


@pytest_asyncio.fixture
async def redis_client(
    settings: Settings, _guard_test_environment: None
) -> AsyncIterator[Redis]:
    from meridian_ams.core.redis.client import build_redis

    client = build_redis(settings)

    try:
        await client.ping()
        await client.flushdb()  # safe: the guard pinned REDIS_DB to the test db

        yield client

    finally:
        await client.aclose()


@pytest.fixture
def app(settings: Settings, engine: AsyncEngine, redis_client: Redis) -> FastAPI:
    """
    A fresh application per test, wired by hand because ASGITransport does not
    run the lifespan. Building it per test keeps dependency overrides and
    app.state from leaking between tests.

    Attaches the engine and Redis client, which the lifespan would build.
    Needs Redis running, but not a migrated database. Tests that reach the
    database through HTTP also request db_override.
    """

    from meridian_ams.main import create_app

    app = create_app(settings)
    app.state.engine = engine
    app.state.redis = redis_client

    return app


@pytest.fixture
def db_override(app: FastAPI, db_test_session: AsyncSession) -> None:
    """Make request handlers use db_test_session instead of opening their own."""

    from meridian_ams.core.dependencies import get_db_session

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_test_session

    app.dependency_overrides[get_db_session] = override_get_db_session


@pytest_asyncio.fixture
async def integration_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        yield client
