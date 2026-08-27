import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.core.caching as cache_module
from src.core.caching import get_settings
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
    ImmutableBase.metadata.create_all(sync_engine)

    yield

    ImmutableBase.metadata.drop_all(sync_engine)
    sync_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def session():
    async with test_engine.connect() as conn:
        await conn.begin()

        test_session = AsyncSession(bind=conn, expire_on_commit=False)

        async def override_get_session():
            yield test_session

        app.dependency_overrides[get_session] = override_get_session

        try:
            yield test_session

        finally:
            try:
                await test_session.close()
                await conn.rollback()

            except Exception as e:
                print(f"Teardown error: {e}")

            finally:
                app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def client(session):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as async_client:
        yield async_client


@pytest_asyncio.fixture(scope="function", autouse=True)
async def flush_cache():
    fresh_client = aioredis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        db=settings.REDIS_DB,
        decode_responses=True,
    )

    cache_module.redis_client = fresh_client

    await fresh_client.flushdb()

    yield

    await fresh_client.flushdb()
    await fresh_client.aclose()
