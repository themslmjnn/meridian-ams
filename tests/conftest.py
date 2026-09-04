import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.caching import get_redis, get_settings
from src.core.dependencies import get_session
from src.database.connection import ImmutableBase
from src.main import app

settings = get_settings()

ASYNC_DB_URL = (
    f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PSSW}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)

SYNC_DB_URL = (
    f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PSSW}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)

test_engine = create_async_engine(url=ASYNC_DB_URL, poolclass=NullPool)


@pytest.fixture(scope="session", autouse=True)
def _guard_test_environment():
    if settings.ENVIRONMENT != "test":
        pytest.exit(
            f"Refusing to run tests: ENVIRONMENT is '{settings.ENVIRONMENT}', "
            "expected 'test'. This guard exists because the test suite "
            "creates and drops the full schema — running it against a "
            "non-test database would destroy real data."
        )


@pytest.fixture(scope="session", autouse=True)
def clear_settings_cache(_guard_test_environment) -> None:  # type: ignore[misc]
    """Clear the lru_cache on get_settings before and after the test session."""
    get_settings.cache_clear()

    yield  # type: ignore[misc]

    get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def create_tables(_guard_test_environment):
    sync_engine = create_engine(SYNC_DB_URL)

    with sync_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.commit()

    ImmutableBase.metadata.create_all(sync_engine)

    yield

    ImmutableBase.metadata.drop_all(sync_engine)
    sync_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session():
    async with test_engine.connect() as conn:
        await conn.begin()

        session = AsyncSession(bind=conn, expire_on_commit=False)

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
async def integration_client(test_session):
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


@pytest_asyncio.fixture(scope="function", autouse=True)
async def override_redis(redis_client):
    async def get_test_redis():
        return redis_client

    app.dependency_overrides[get_redis] = get_test_redis

    yield

    app.dependency_overrides.pop(get_redis, None)
