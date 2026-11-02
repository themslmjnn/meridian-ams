import asyncio
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError

from meridian_ams.api import health


@pytest.fixture
def database_ping(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    ping = AsyncMock()
    monkeypatch.setattr(health, "_ping_database", ping)

    return ping


@pytest.fixture
def redis_ping(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    ping = AsyncMock()
    monkeypatch.setattr(health, "_ping_redis", ping)

    return ping


@pytest_asyncio.fixture
async def client(database_ping, redis_ping):
    app = FastAPI()

    app.include_router(health.router)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


class TestLiveness:
    async def test_returns_ok(self, client: AsyncClient):
        response = await client.get("/health/live")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestReadiness:
    async def test_all_checks_passing(self, client: AsyncClient):
        response = await client.get("/health/ready")

        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["checks"]["database"]["status"] == "ok"
        assert body["checks"]["redis"]["status"] == "ok"
        assert body["checks"]["database"]["duration_ms"] >= 0
        assert body["checks"]["redis"]["duration_ms"] >= 0

    @pytest.mark.parametrize(
        "error",
        [RuntimeError("boom"), ConnectionRefusedError("refused")],
        ids=["runtime_error", "connection_refused"],
    )
    async def test_database_failure_returns_503(
        self, client: AsyncClient, database_ping, error
    ):
        database_ping.side_effect = error

        response = await client.get("/health/ready")

        body = response.json()

        assert response.status_code == 503
        assert body["status"] == "error"
        assert body["checks"]["database"]["status"] == "error"
        assert body["checks"]["redis"]["status"] == "ok"

    async def test_redis_failure_returns_503(self, client: AsyncClient, redis_ping):
        redis_ping.side_effect = RedisConnectionError("down")

        response = await client.get("/health/ready")

        body = response.json()

        assert response.status_code == 503
        assert body["status"] == "error"
        assert body["checks"]["database"]["status"] == "ok"
        assert body["checks"]["redis"]["status"] == "error"

    async def test_both_failing_reports_both(
        self, client: AsyncClient, database_ping, redis_ping
    ):
        database_ping.side_effect = RuntimeError("db down")
        redis_ping.side_effect = RedisConnectionError("redis down")

        response = await client.get("/health/ready")

        body = response.json()

        assert response.status_code == 503
        assert body["checks"]["database"]["status"] == "error"
        assert body["checks"]["redis"]["status"] == "error"

    async def test_slow_check_counts_as_failed(
        self, client: AsyncClient, database_ping, monkeypatch
    ):
        async def hang(request):
            await asyncio.sleep(5)

        database_ping.side_effect = hang
        monkeypatch.setattr(health, "CHECK_TIMEOUT_SECONDS", 0.05)

        response = await client.get("/health/ready")

        assert response.status_code == 503
        assert response.json()["checks"]["database"]["status"] == "error"


async def test_ready_with_real_database_and_redis(integration_client: AsyncClient):
    response = await integration_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
