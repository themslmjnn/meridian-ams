import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from redis.exceptions import RedisError
from starlette.responses import Response
from structlog.testing import capture_logs

from src.core.exceptions import register_exception_handlers
from src.core.middleware import (
    CorrelationIDMiddleware,
    ExceptionHandlerMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)

route_logger = structlog.get_logger("test.route")


def build_app(*, hsts: bool = False, with_exception_middleware: bool = True) -> FastAPI:
    """
    Bare app. Last added runs first, so this matches create_app()'s order:
    Correlation -> Logging -> Security -> ExceptionHandler.
    """

    app = FastAPI()
    register_exception_handlers(app)

    if with_exception_middleware:
        app.add_middleware(ExceptionHandlerMiddleware)

    app.add_middleware(SecurityHeadersMiddleware, hsts=hsts)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    @app.get("/log")
    async def log_inside_handler():
        route_logger.info("inside_handler")
        return {"ok": True}

    @app.get("/cache-custom")
    async def cache_custom():
        return Response(content="x", headers={"Cache-Control": "max-age=60"})

    @app.get("/runtime-error")
    async def runtime_error():
        raise RuntimeError("secret-detail")

    @app.get("/redis-error")
    async def redis_error():
        raise RedisError("AUTH failed: wrong password")

    @app.get("/health/live")
    async def health_live():
        return {"status": "ok"}

    @app.get("/health/down")
    async def health_down():
        return JSONResponse(status_code=503, content={"status": "down"})

    return app


@asynccontextmanager
async def open_client(app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


@pytest_asyncio.fixture
async def client():
    async with open_client(build_app()) as c:
        yield c


@pytest.fixture
def captured_logs():
    structlog.contextvars.clear_contextvars()
    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        yield logs


def events_named(logs: list[dict], name: str) -> list[dict]:
    return [entry for entry in logs if entry["event"] == name]


class TestCorrelationID:
    async def test_valid_client_id_is_echoed(self, client):
        response = await client.get("/ok", headers={"X-Request-ID": "abc-123_X.y"})

        assert response.headers["X-Request-ID"] == "abc-123_X.y"

    async def test_missing_id_generates_uuid4(self, client):
        response = await client.get("/ok")

        parsed = uuid.UUID(response.headers["X-Request-ID"])
        assert parsed.version == 4

    async def test_generated_ids_differ_between_requests(self, client):
        first = await client.get("/ok")
        second = await client.get("/ok")

        assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]

    @pytest.mark.parametrize(
        "bad_id", ["x" * 65, "has space", "semi;colon", "slash/inside", ""]
    )
    async def test_invalid_client_id_is_replaced(self, client, bad_id):
        response = await client.get("/ok", headers={"X-Request-ID": bad_id})

        returned = response.headers["X-Request-ID"]
        assert returned != bad_id
        assert uuid.UUID(returned).version == 4

    async def test_id_boundary_64_chars_accepted(self, client):
        response = await client.get("/ok", headers={"X-Request-ID": "a" * 64})

        assert response.headers["X-Request-ID"] == "a" * 64

    async def test_request_id_reaches_logs_emitted_inside_the_handler(
        self, client, captured_logs
    ):
        response = await client.get("/log")

        inside = events_named(captured_logs, "inside_handler")
        assert len(inside) == 1
        assert inside[0]["request_id"] == response.headers["X-Request-ID"]

    async def test_context_is_cleared_after_the_request(self, client, captured_logs):
        await client.get("/ok")

        assert structlog.contextvars.get_contextvars() == {}

    async def test_context_is_cleared_even_when_the_request_fails(
        self, client, captured_logs
    ):
        await client.get("/runtime-error")

        assert structlog.contextvars.get_contextvars() == {}

    async def test_environment_is_not_bound_by_the_middleware(
        self, client, captured_logs
    ):
        await client.get("/log")

        inside = events_named(captured_logs, "inside_handler")[0]
        assert "environment" not in inside


class TestRequestLogging:
    async def test_logs_method_path_status_and_duration(self, client, captured_logs):
        await client.get("/ok")

        entry = events_named(captured_logs, "request_handled")[0]
        assert entry["method"] == "GET"
        assert entry["path"] == "/ok"
        assert entry["status_code"] == 200
        assert isinstance(entry["duration_ms"], float)
        assert entry["duration_ms"] >= 0
        assert entry["log_level"] == "info"

    async def test_log_line_carries_the_response_request_id(
        self, client, captured_logs
    ):
        response = await client.get("/ok")

        entry = events_named(captured_logs, "request_handled")[0]
        assert entry["request_id"] == response.headers["X-Request-ID"]

    async def test_one_log_line_per_request(self, client, captured_logs):
        await client.get("/ok")
        await client.get("/ok")

        assert len(events_named(captured_logs, "request_handled")) == 2

    async def test_healthy_probe_logs_at_debug(self, client, captured_logs):
        await client.get("/health/live")

        entry = events_named(captured_logs, "request_handled")[0]
        assert entry["status_code"] == 200
        assert entry["log_level"] == "debug"

    async def test_failing_probe_still_logs_at_info(self, client, captured_logs):
        await client.get("/health/down")

        entry = events_named(captured_logs, "request_handled")[0]
        assert entry["status_code"] == 503
        assert entry["log_level"] == "info"

    async def test_unhandled_error_is_logged_as_500_in_full_stack(
        self, client, captured_logs
    ):
        await client.get("/runtime-error")

        entry = events_named(captured_logs, "request_handled")[0]
        assert entry["status_code"] == 500

    async def test_escaping_exception_is_logged_as_500_without_exception_middleware(
        self, captured_logs
    ):
        app = build_app(with_exception_middleware=False)

        async with open_client(app) as c:
            await c.get("/runtime-error")

        entry = events_named(captured_logs, "request_handled")[0]
        assert entry["status_code"] == 500
        assert entry["path"] == "/runtime-error"


class TestExceptionHandlerMiddleware:
    async def test_unhandled_error_returns_standard_500(self, client):
        response = await client.get("/runtime-error")

        assert response.status_code == 500
        assert response.json() == {
            "error_code": "INTERNAL_SERVER_ERROR",
            "detail": "An unexpected error occurred.",
        }

    async def test_unhandled_error_does_not_leak_detail(self, client):
        response = await client.get("/runtime-error")

        assert "secret-detail" not in response.text
        assert "RuntimeError" not in response.text

    async def test_unhandled_error_is_logged_and_sent_to_sentry(
        self, client, captured_logs, mocker
    ):
        capture = mocker.patch("src.core.middleware.sentry_sdk.capture_exception")

        response = await client.get("/runtime-error")

        logged = events_named(captured_logs, "unhandled_exception")
        assert len(logged) == 1
        assert logged[0]["path"] == "/runtime-error"
        assert logged[0]["method"] == "GET"
        assert logged[0]["request_id"] == response.headers["X-Request-ID"]
        capture.assert_called_once()
        assert isinstance(capture.call_args.args[0], RuntimeError)

    async def test_redis_error_returns_503_not_500(self, client):
        response = await client.get("/redis-error")

        assert response.status_code == 503
        assert response.json() == {
            "error_code": "SERVICE_UNAVAILABLE",
            "detail": "Required service is temporarily unavailable",
        }

    async def test_redis_error_does_not_leak_detail(self, client):
        response = await client.get("/redis-error")

        assert "AUTH failed" not in response.text
        assert "wrong password" not in response.text

    async def test_redis_error_is_not_reported_as_unhandled(
        self, client, captured_logs, mocker
    ):
        capture = mocker.patch("src.core.middleware.sentry_sdk.capture_exception")

        await client.get("/redis-error")

        assert events_named(captured_logs, "unhandled_exception") == []
        assert len(events_named(captured_logs, "redis_critical_failure")) == 1
        capture.assert_not_called()

    async def test_error_responses_carry_request_id_and_security_headers(self, client):
        for path in ("/runtime-error", "/redis-error"):
            response = await client.get(path)

            assert response.headers.get("X-Request-ID")
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["X-Frame-Options"] == "DENY"


class TestSecurityHeaders:
    async def test_standard_headers_present(self, client):
        response = await client.get("/ok")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    async def test_cache_control_defaults_to_no_store(self, client):
        response = await client.get("/ok")

        assert response.headers["Cache-Control"] == "no-store"

    async def test_handler_cache_control_is_preserved(self, client):
        response = await client.get("/cache-custom")

        assert response.headers["Cache-Control"] == "max-age=60"

    async def test_hsts_absent_by_default(self, client):
        response = await client.get("/ok")

        assert "Strict-Transport-Security" not in response.headers

    async def test_hsts_present_when_enabled(self):
        async with open_client(build_app(hsts=True)) as c:
            response = await c.get("/ok")

        assert response.headers["Strict-Transport-Security"] == "max-age=31536000"

    async def test_hsts_also_on_error_responses_when_enabled(self):
        async with open_client(build_app(hsts=True)) as c:
            response = await c.get("/runtime-error")

        assert response.headers["Strict-Transport-Security"] == "max-age=31536000"


class TestRealAppWiring:
    def test_security_headers_hsts_follows_environment(self):
        from src.core.config import get_settings
        from src.main import create_app

        entry = next(
            m
            for m in create_app().user_middleware
            if m.cls is SecurityHeadersMiddleware
        )
        options = getattr(entry, "kwargs", None) or getattr(entry, "options", {})

        assert options.get("hsts") is get_settings().IS_PRODUCTION_LIKE
