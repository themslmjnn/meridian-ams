from unittest.mock import patch

import pytest
import structlog
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from structlog.testing import capture_logs

from meridian_ams.core.middleware import (
    CorrelationIDMiddleware,
    ExceptionHandlerMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)

ALLOWED_ORIGIN = "http://localhost:3000"


def _build_app(*, hsts: bool = False) -> FastAPI:
    """Tiny app with the same middleware order as create_app."""

    app = FastAPI()

    app.add_middleware(ExceptionHandlerMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[ALLOWED_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=hsts)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/context")
    async def context() -> dict[str, str]:
        return {"request_id": structlog.contextvars.get_contextvars()["request_id"]}

    @app.get("/custom-cache")
    async def custom_cache(response: Response) -> dict[str, str]:
        response.headers["Cache-Control"] = "max-age=60"
        return {"status": "ok"}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/redis-down")
    async def redis_down() -> None:
        raise RedisError("connection refused")

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def health_ready(response: Response) -> dict[str, str]:
        response.status_code = 503
        return {"status": "down"}

    return app


@pytest.fixture(autouse=True)
def reset_structlog():
    structlog.reset_defaults()

    yield

    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app(), raise_server_exceptions=False)


class TestCorrelationID:
    def test_generates_request_id_when_missing(self, client):
        response = client.get("/ok")

        assert len(response.headers["X-Request-ID"]) == 36

    def test_echoes_valid_client_request_id(self, client):
        response = client.get("/ok", headers={"X-Request-ID": "my-trace_1.2"})

        assert response.headers["X-Request-ID"] == "my-trace_1.2"

    def test_replaces_invalid_client_request_id(self, client):
        response = client.get("/ok", headers={"X-Request-ID": "bad id with spaces"})

        assert response.headers["X-Request-ID"] != "bad id with spaces"
        assert len(response.headers["X-Request-ID"]) == 36

    def test_replaces_too_long_client_request_id(self, client):
        response = client.get("/ok", headers={"X-Request-ID": "a" * 65})

        assert response.headers["X-Request-ID"] != "a" * 65

    def test_request_id_is_bound_for_the_handler(self, client):
        response = client.get("/context", headers={"X-Request-ID": "trace-42"})

        assert response.json() == {"request_id": "trace-42"}


class TestRequestLogging:
    def test_logs_request_fields_at_info(self, client):
        with capture_logs() as logs:
            client.get("/ok")

        (entry,) = [e for e in logs if e["event"] == "request_handled"]
        assert entry["log_level"] == "info"
        assert entry["method"] == "GET"
        assert entry["path"] == "/ok"
        assert entry["status_code"] == 200
        assert entry["duration_ms"] >= 0

    def test_healthy_health_probe_logs_at_debug(self, client):
        with capture_logs() as logs:
            client.get("/health/live")

        (entry,) = [e for e in logs if e["event"] == "request_handled"]
        assert entry["log_level"] == "debug"

    def test_failing_health_probe_logs_at_info(self, client):
        with capture_logs() as logs:
            client.get("/health/ready")

        (entry,) = [e for e in logs if e["event"] == "request_handled"]
        assert entry["log_level"] == "info"
        assert entry["status_code"] == 503

    def test_unhandled_error_is_logged_with_real_status(self, client):
        with capture_logs() as logs:
            client.get("/boom")

        (entry,) = [e for e in logs if e["event"] == "request_handled"]
        assert entry["status_code"] == 500


class TestExceptionHandler:
    def test_unhandled_error_returns_standard_500(self, client):
        response = client.get("/boom")

        assert response.status_code == 500
        assert response.json() == {
            "error_code": "INTERNAL_SERVER_ERROR",
            "detail": "An unexpected error occurred.",
        }
        assert "secret internal detail" not in response.text

    def test_unhandled_error_is_reported_to_sentry_once(self, client):
        with patch(
            "meridian_ams.core.middleware.sentry_sdk.capture_exception"
        ) as capture:
            client.get("/boom")

        capture.assert_called_once()

    def test_redis_error_returns_503(self, client):
        response = client.get("/redis-down")

        assert response.status_code == 503

    def test_500_still_carries_request_id_security_and_cors_headers(self, client):
        response = client.get(
            "/boom",
            headers={"Origin": ALLOWED_ORIGIN, "X-Request-ID": "trace-500"},
        )

        assert response.status_code == 500
        assert response.headers["X-Request-ID"] == "trace-500"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN


class TestSecurityHeaders:
    def test_adds_standard_headers(self, client):
        response = client.get("/ok")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response.headers["Cache-Control"] == "no-store"

    def test_hsts_is_absent_by_default(self, client):
        response = client.get("/ok")

        assert "Strict-Transport-Security" not in response.headers

    def test_hsts_is_added_when_enabled(self):
        client = TestClient(_build_app(hsts=True))

        response = client.get("/ok")

        assert response.headers["Strict-Transport-Security"] == "max-age=31536000"

    def test_handler_cache_control_is_not_overridden(self, client):
        response = client.get("/custom-cache")

        assert response.headers["Cache-Control"] == "max-age=60"
