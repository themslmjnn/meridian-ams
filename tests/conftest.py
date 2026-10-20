from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import NullPool

import src.models  # noqa: F401  (registers every model on the metadata)
from src.auth.tokens import create_access_token
from src.core.caching import close_redis, init_redis
from src.core.config import Settings, get_settings
from src.core.dependencies import get_db_session
from src.database.connection import ImmutableBase, engine
from src.main import app
from src.users.models.credentials import UserCredentials
from src.users.repository.session import UserSessionRepository
from tests.factories import (
    make_director,
    make_guardian,
    make_student,
    make_system_admin,
    make_teacher,
)

settings = get_settings()

SYNC_DB_URL = URL.create(
    "postgresql+psycopg2",
    username=settings.DB_USER,
    password=settings.DB_PASSWORD.get_secret_value(),
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    database=settings.DB_NAME,
)


@pytest.fixture(scope="session", autouse=True)
def _guard_test_environment() -> None:
    problems: list[str] = []

    if settings.ENVIRONMENT != "test":
        problems.append(f"ENVIRONMENT is '{settings.ENVIRONMENT}', expected 'test'")

    if not settings.DB_NAME.lower().endswith("_test"):
        problems.append(f"DB_NAME '{settings.DB_NAME}' must end with '_test'")

    if settings.REDIS_DB != 1:
        problems.append(f"REDIS_DB is {settings.REDIS_DB}, expected 1 for tests")

    if not isinstance(engine.sync_engine.pool, NullPool):
        problems.append("app engine is pooled; tests require NullPool")

    if problems:
        pytest.exit("Refusing to run tests: " + "; ".join(problems), returncode=2)


@pytest.fixture(scope="session")  # not autouse: only DB-backed tests pay for it
def create_tables(_guard_test_environment: None) -> Iterator[None]:
    sync_engine = create_engine(SYNC_DB_URL)

    try:
        with sync_engine.begin() as conn:
            db_name = conn.scalar(text("SELECT current_database()"))

            if not (db_name.lower() or "").endswith("_test"):
                pytest.exit(
                    f"Refusing to reset database '{db_name}': "
                    "name must end with '_test'",
                    returncode=2,
                )

            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

            ImmutableBase.metadata.create_all(conn)

        yield

    finally:
        sync_engine.dispose()


@pytest_asyncio.fixture
async def db_test_session(create_tables: None) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        outer = await conn.begin()

        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )

        async def override_get_db_session() -> AsyncIterator[AsyncSession]:
            yield session

        app.dependency_overrides[get_db_session] = override_get_db_session

        try:
            yield session

        finally:
            app.dependency_overrides.pop(get_db_session, None)

            await session.close()
            await outer.rollback()


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[aioredis.Redis]:
    app.state.settings = settings  # init_redis reads it; lifespan doesn't run here

    await init_redis(app)

    client: aioredis.Redis = app.state.redis

    try:
        await client.flushdb()

        yield client

    finally:
        await close_redis(app)

        del app.state.redis


@pytest_asyncio.fixture
async def integration_client(
    db_test_session: AsyncSession, redis_client: aioredis.Redis
) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        yield client


@pytest.fixture
def database_health_mock(mocker):
    return mocker.patch(
        "src.api.health._check_database",
        new_callable=AsyncMock,
        return_value={"status": "ok", "duration_ms": 1.0},
    )


@pytest.fixture
def redis_health_mock(mocker):
    return mocker.patch(
        "src.api.health._check_redis",
        new_callable=AsyncMock,
        return_value={"status": "ok", "duration_ms": 1.0},
    )


_BASE: dict[str, object] = {
    "ENVIRONMENT": "test",
    "DB_HOST": "localhost",
    "DB_USER": "u",
    "DB_PASSWORD": "p",
    "DB_NAME": "meridian_test",
    "REDIS_HOST": "localhost",
    "REDIS_DB": 1,
    "JWT_SECRET_KEY": "a" * 64,
    "CURSOR_SECRET_KEY": "b" * 64,
    "WORK_EMAIL_DOMAIN": "meridian.edu",
    # valid for staging/production too:
    "APP_URL": "https://api.meridian.edu",
    "ALLOWED_HOSTS": ["api.meridian.edu"],
    "CORS_ORIGINS": ["https://app.meridian.edu"],
    "EMAIL_API_KEY": "re_live_key",
    "MAIL_FROM": "noreply@meridian.edu",
}


@pytest.fixture
def make_settings(monkeypatch):
    """Build Settings from explicit values only; ignores env vars and .env files."""

    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)

    def _make(_drop: tuple[str, ...] = (), **overrides: object) -> Settings:
        values = {**_BASE, **overrides}
        for key in _drop:
            values.pop(key, None)

        return Settings(_env_file=None, **values)

    return _make


async def make_auth_header(
    db_test_session: AsyncSession, credentials: UserCredentials
) -> dict:
    user_session = await UserSessionRepository.get_by_credentials_id(
        db_test_session, credentials.id
    )

    access_token = create_access_token(
        public_id=credentials.public_id,
        role=credentials.role,
        account_type=credentials.account_type,
        session_id=user_session.id,
        access_token_version=user_session.access_token_version,
    )

    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture
async def system_admin(db_test_session):
    return await make_system_admin(db_test_session)


@pytest_asyncio.fixture
async def director(db_test_session):
    return await make_director(db_test_session)


@pytest_asyncio.fixture
async def teacher(db_test_session):
    return await make_teacher(db_test_session)


@pytest_asyncio.fixture
async def student(db_test_session):
    return await make_student(db_test_session)


@pytest_asyncio.fixture
async def guardian(db_test_session):
    return await make_guardian(db_test_session)
