from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.auth.schemas import CreateAccessToken
from src.core.caching import get_redis
from src.core.config import Settings, get_settings
from src.core.dependencies import get_session
from src.core.security import create_access_token
from src.database.connection import ImmutableBase
from src.main import app
from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserSessionRepository
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

test_engine = create_async_engine(url=settings.DATABASE_URL, poolclass=NullPool)


@pytest.fixture(scope="session", autouse=True)
def _guard_test_environment():
    problems = []

    if settings.ENVIRONMENT != "test":
        problems.append(f"ENVIRONMENT is '{settings.ENVIRONMENT}', expected 'test'")
    if "test" not in settings.DB_NAME.lower():
        problems.append(
            f"DB_NAME '{settings.DB_NAME}' does not look like a test database"
        )
    if settings.REDIS_DB != 1:
        problems.append(f"REDIS_DB is {settings.REDIS_DB}, expected 1 for tests")

    if problems:
        pytest.exit("Refusing to run tests: " + "; ".join(problems))


@pytest.fixture(scope="session", autouse=True)
def clear_settings_cache(_guard_test_environment) -> None:  # type: ignore[misc]
    """Clear the lru_cache on get_settings before and after the test session."""

    get_settings.cache_clear()

    yield  # type: ignore[misc]

    get_settings.cache_clear()


@pytest.fixture(scope="session")  # no autouse: only DB-backed tests pay for it
def create_tables(_guard_test_environment):
    sync_engine = create_engine(SYNC_DB_URL)

    with sync_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.commit()

    ImmutableBase.metadata.drop_all(sync_engine)  # clear leftovers from a crashed run
    ImmutableBase.metadata.create_all(sync_engine)

    yield

    ImmutableBase.metadata.drop_all(sync_engine)
    sync_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session(create_tables):
    async with test_engine.connect() as conn:
        await conn.begin()

        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )

        async def override_get_session():
            yield session

        app.dependency_overrides[get_session] = override_get_session

        try:
            yield session

        finally:
            try:
                await session.close()
                await conn.rollback()

            except Exception as e:
                print(f"Teardown error: {e}")

            finally:
                app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def integration_client(test_session, override_redis):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as async_client:
        yield async_client


@pytest_asyncio.fixture(scope="function")
async def redis_client():
    client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )

    await client.flushdb()

    yield client

    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture(scope="function")
async def override_redis(redis_client):
    async def get_test_redis():
        return redis_client

    app.dependency_overrides[get_redis] = get_test_redis

    yield

    app.dependency_overrides.pop(get_redis, None)


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
    session: AsyncSession, user_credentials: UserCredentials
) -> dict:
    user_session = await UserSessionRepository.get_by_credentials_id(
        session, user_credentials.id
    )

    token = create_access_token(
        CreateAccessToken(
            public_id=user_credentials.public_id,
            role=user_credentials.role,
            account_type=user_credentials.account_type,
            session_id=user_session.id,
            access_token_version=user_session.access_token_version,
        )
    )

    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def system_admin(test_session):
    return await make_system_admin(test_session)


@pytest_asyncio.fixture
async def director(test_session):
    return await make_director(test_session)


@pytest_asyncio.fixture
async def teacher(test_session):
    return await make_teacher(test_session)


@pytest_asyncio.fixture
async def student(test_session):
    return await make_student(test_session)


@pytest_asyncio.fixture
async def guardian(test_session):
    return await make_guardian(test_session)
