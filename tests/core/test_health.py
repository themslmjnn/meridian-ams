from httpx import AsyncClient


async def test_live_returns_200(integration_client: AsyncClient):
    response = await integration_client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_live_response_has_request_id(integration_client: AsyncClient):
    """Liveness response must carry X-Request-ID like every other response."""

    response = await integration_client.get("/health/live")

    assert "x-request-id" in response.headers


async def test_ready_returns_200_when_both_healthy(
    integration_client: AsyncClient, database_health_mock, redis_health_mock
):
    redis_health_mock.return_value = {"status": "ok", "duration_ms": 0.5}

    response = await integration_client.get("/health/ready")

    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"


async def test_ready_response_shape_has_duration_ms(
    integration_client: AsyncClient, database_health_mock, redis_health_mock
):
    """Each check result must include duration_ms."""

    database_health_mock.return_value = {"status": "ok", "duration_ms": 3.5}
    redis_health_mock.return_value = {"status": "ok", "duration_ms": 1.2}

    response = await integration_client.get("/health/ready")

    body = response.json()

    assert "duration_ms" in body["checks"]["database"]
    assert "duration_ms" in body["checks"]["redis"]


async def test_ready_returns_503_when_db_unreachable(
    integration_client: AsyncClient, database_health_mock, redis_health_mock
):
    database_health_mock.return_value = {
        "status": "error",
        "duration_ms": 5.0,
        "error": "connection refused",
    }
    redis_health_mock.return_value = {"status": "ok", "duration_ms": 0.5}

    response = await integration_client.get("/health/ready")

    body = response.json()

    assert response.status_code == 503
    assert body["status"] == "error"
    assert body["checks"]["database"]["status"] == "error"
    assert body["checks"]["redis"]["status"] == "ok"


async def test_ready_returns_503_when_redis_unreachable(
    integration_client: AsyncClient, database_health_mock, redis_health_mock
):
    redis_health_mock.return_value = {
        "status": "error",
        "duration_ms": 2.0,
        "error": "connection refused",
    }

    response = await integration_client.get("/health/ready")

    body = response.json()

    assert response.status_code == 503
    assert body["status"] == "error"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "error"


async def test_ready_returns_503_when_both_unhealthy(
    integration_client: AsyncClient, database_health_mock, redis_health_mock
):
    database_health_mock.return_value = {"status": "error", "duration_ms": 5.0}
    redis_health_mock.return_value = {"status": "error", "duration_ms": 2.0}

    response = await integration_client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "error"


async def test_ready_includes_both_check_keys_regardless_of_failure(
    integration_client: AsyncClient, database_health_mock, redis_health_mock
):
    """Both check keys must always be present in the response body."""

    database_health_mock.return_value = {"status": "error", "duration_ms": 5.0}
    redis_health_mock.return_value = {"status": "error", "duration_ms": 2.0}

    response = await integration_client.get("/health/ready")

    body = response.json()

    assert "database" in body["checks"]
    assert "redis" in body["checks"]


async def test_ready_both_checks_run_when_db_raises(
    integration_client: AsyncClient, database_health_mock, redis_health_mock
):
    """
    asyncio.gather(return_exceptions=True) ensures both checks always run.
    Even if _check_database raises, _check_redis must still be called.
    """

    database_health_mock.side_effect = Exception("db exploded")
    redis_health_mock.return_value = {"status": "ok", "duration_ms": 0.5}

    response = await integration_client.get("/health/ready")

    assert response.status_code == 503
    redis_health_mock.assert_called_once()


async def test_ready_both_checks_run_when_redis_raises(
    integration_client: AsyncClient, database_health_mock, redis_health_mock
):
    """Both checks run even when Redis raises — DB check is not skipped."""

    redis_health_mock.side_effect = Exception("db exploded")

    response = await integration_client.get("/health/ready")

    assert response.status_code == 503
    database_health_mock.assert_called_once()
