import re

import pytest
import pytest_asyncio
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, field_validator
from redis.exceptions import RedisError
from starlette.middleware.cors import CORSMiddleware
from structlog.testing import capture_logs

from src.core.exceptions import AppException, register_exception_handlers
from src.core.middleware import (
    CorrelationIDMiddleware,
    ExceptionHandlerMiddleware,
    SecurityHeadersMiddleware,
)


class ThingNotFoundError(AppException):
    status_code = 404
    error_code = "THING_NOT_FOUND"
    detail = "Thing not found"


class ThingConflictError(AppException):
    status_code = 409
    error_code = "THING_CONFLICT"
    detail = "Thing already exists"


class ThingForbiddenError(AppException):
    status_code = 403
    error_code = "THING_FORBIDDEN"
    detail = "Not allowed"


class StrictBody(BaseModel):
    name: str
    age: int


class PositiveBody(BaseModel):
    age: int

    @field_validator("age")
    @classmethod
    def must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("age must be positive")

        return v


def build_app() -> FastAPI:
    """Bare app: the handlers and middleware under test, nothing else."""
    app = FastAPI()
    register_exception_handlers(app)

    # Same relative order as create_app(): last added runs first.
    app.add_middleware(ExceptionHandlerMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIDMiddleware)

    @app.get("/not-found")
    async def not_found():
        raise ThingNotFoundError()

    @app.get("/conflict")
    async def conflict():
        raise ThingConflictError()

    @app.get("/forbidden")
    async def forbidden():
        raise ThingForbiddenError()

    @app.get("/custom-detail")
    async def custom_detail():
        raise ThingNotFoundError("Custom message")

    @app.get("/empty-detail")
    async def empty_detail():
        raise ThingNotFoundError("")

    @app.get("/unhandled")
    async def unhandled():
        raise RuntimeError("secret internal error message")

    @app.get("/redis-error")
    async def redis_error():
        raise RedisError("AUTH failed: wrong password")

    @app.post("/validate")
    async def validate(body: StrictBody):
        return body

    @app.post("/validate-custom")
    async def validate_custom(body: PositiveBody):
        return body

    return app


@pytest_asyncio.fixture
async def exception_client():
    async with AsyncClient(
        transport=ASGITransport(app=build_app(), raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
def captured_logs():
    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        yield logs


class TestAppExceptionDefinition:
    def test_direct_instantiation_raises(self):
        with pytest.raises(TypeError, match="must not be raised directly"):
            AppException()

    @pytest.mark.parametrize("bad_status", ["404", True, 200, 600, None])
    def test_invalid_status_code_rejected(self, bad_status):
        with pytest.raises(TypeError, match="status_code"):

            class Bad(AppException):
                status_code = bad_status
                error_code = "BAD"
                detail = "bad"

    @pytest.mark.parametrize("bad_code", ["", 404, None])
    def test_invalid_error_code_rejected(self, bad_code):
        with pytest.raises(TypeError, match="error_code"):

            class Bad(AppException):
                status_code = 400
                error_code = bad_code
                detail = "bad"

    @pytest.mark.parametrize("bad_detail", ["", 123, None])
    def test_invalid_detail_rejected(self, bad_detail):
        with pytest.raises(TypeError, match="detail"):

            class Bad(AppException):
                status_code = 400
                error_code = "BAD"
                detail = bad_detail

    def test_missing_attributes_rejected(self):
        with pytest.raises(TypeError):

            class Bad(AppException):
                status_code = 400

    def test_extra_public_attribute_rejected(self):
        with pytest.raises(TypeError, match=re.escape("['retry_after']")):

            class Bad(AppException):
                status_code = 429
                error_code = "RATE_LIMITED"
                detail = "Slow down"
                retry_after = 30

    def test_private_attributes_and_methods_allowed(self):
        class Fine(AppException):
            status_code = 400
            error_code = "FINE"
            detail = "fine"
            _internal = 1

            def helper(self) -> str:
                return "ok"

        assert Fine().helper() == "ok"

    def test_concrete_intermediate_base_accepted(self):
        class SpecificNotFound(ThingNotFoundError):
            error_code = "SPECIFIC_NOT_FOUND"
            detail = "Specific thing not found"

        exc = SpecificNotFound()

        assert exc.status_code == 404
        assert exc.error_code == "SPECIFIC_NOT_FOUND"
        assert exc.detail == "Specific thing not found"


class TestAppExceptionInstance:
    def test_default_detail_comes_from_class(self):
        assert ThingNotFoundError().detail == "Thing not found"

    def test_custom_detail_overrides_default(self):
        exc = ThingNotFoundError("Custom")

        assert exc.detail == "Custom"
        assert str(exc) == "Custom"

    def test_empty_detail_is_preserved(self):
        assert ThingNotFoundError("").detail == ""


class TestAppExceptionHandler:
    async def test_returns_correct_shape(self, exception_client: AsyncClient):
        response = await exception_client.get("/not-found")

        assert response.status_code == 404
        assert response.json() == {
            "error_code": "THING_NOT_FOUND",
            "detail": "Thing not found",
        }

    @pytest.mark.parametrize(
        ("path", "status", "code"),
        [
            ("/not-found", 404, "THING_NOT_FOUND"),
            ("/conflict", 409, "THING_CONFLICT"),
            ("/forbidden", 403, "THING_FORBIDDEN"),
        ],
    )
    async def test_status_code_and_error_code_respected(
        self, exception_client: AsyncClient, path, status, code
    ):
        response = await exception_client.get(path)

        assert response.status_code == status
        assert response.json()["error_code"] == code

    async def test_body_has_exactly_two_keys(self, exception_client: AsyncClient):
        response = await exception_client.get("/not-found")

        assert set(response.json().keys()) == {"error_code", "detail"}

    async def test_custom_detail_in_response(self, exception_client: AsyncClient):
        response = await exception_client.get("/custom-detail")

        assert response.json()["detail"] == "Custom message"

    async def test_empty_detail_in_response(self, exception_client: AsyncClient):
        response = await exception_client.get("/empty-detail")

        assert response.json()["detail"] == ""


class TestValidationErrorHandler:
    async def test_returns_422_shape(self, exception_client: AsyncClient):
        response = await exception_client.post(
            "/validate", json={"name": "Alice", "age": "x"}
        )

        body = response.json()

        assert response.status_code == 422
        assert set(body.keys()) == {"error_code", "detail", "errors"}
        assert body["error_code"] == "VALIDATION_ERROR"
        assert body["detail"] == "Request validation failed"
        assert len(body["errors"]) == 1

    async def test_error_items_have_exact_keys_and_field_path(
        self, exception_client: AsyncClient
    ):
        response = await exception_client.post(
            "/validate", json={"name": "Alice", "age": "x"}
        )

        error = response.json()["errors"][0]

        assert set(error.keys()) == {"field", "message", "type"}
        assert error["field"] == "body -> age"

    async def test_missing_field_reported(self, exception_client: AsyncClient):
        response = await exception_client.post("/validate", json={"name": "Alice"})

        body = response.json()

        assert response.status_code == 422
        assert body["errors"][0]["field"] == "body -> age"
        assert body["errors"][0]["type"] == "missing"

    async def test_multiple_errors_all_reported(self, exception_client: AsyncClient):
        response = await exception_client.post(
            "/validate", json={"name": 1, "age": "x"}
        )

        fields = {e["field"] for e in response.json()["errors"]}

        assert fields == {"body -> name", "body -> age"}

    async def test_value_error_prefix_stripped(self, exception_client: AsyncClient):
        response = await exception_client.post("/validate-custom", json={"age": -1})

        error = response.json()["errors"][0]

        assert error["message"] == "age must be positive"
        assert not error["message"].startswith("Value error")


class TestUnhandledExceptionMiddleware:
    async def test_returns_500_standard_shape(self, exception_client: AsyncClient):
        response = await exception_client.get("/unhandled")

        assert response.status_code == 500
        assert response.json() == {
            "error_code": "INTERNAL_SERVER_ERROR",
            "detail": "An unexpected error occurred.",
        }

    async def test_does_not_leak_detail(self, exception_client: AsyncClient):
        response = await exception_client.get("/unhandled")

        text = response.text

        assert "secret internal error message" not in text
        assert "RuntimeError" not in text

    async def test_response_has_request_id_and_security_headers(
        self, exception_client: AsyncClient
    ):
        response = await exception_client.get("/unhandled")

        assert response.headers.get("X-Request-ID")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

    async def test_log_event_includes_request_id(
        self, exception_client: AsyncClient, captured_logs
    ):
        response = await exception_client.get("/unhandled")

        events = [e for e in captured_logs if e["event"] == "unhandled_exception"]

        assert len(events) == 1
        assert events[0]["path"] == "/unhandled"
        assert events[0]["method"] == "GET"
        assert events[0]["request_id"] == response.headers["X-Request-ID"]


class TestMiddlewareOrderInRealApp:
    def test_exception_middleware_inside_cors_and_outside_limiter(self):
        from slowapi.middleware import SlowAPIMiddleware

        from src.main import create_app

        # user_middleware is ordered outermost-first.
        order = [m.cls for m in create_app().user_middleware]

        assert (
            order.index(CorrelationIDMiddleware)
            < order.index(SecurityHeadersMiddleware)
            < order.index(CORSMiddleware)
            < order.index(ExceptionHandlerMiddleware)
            < order.index(SlowAPIMiddleware)
        )


class TestRedisErrorHandler:
    async def test_returns_503(self, exception_client: AsyncClient):
        response = await exception_client.get("/redis-error")

        assert response.status_code == 503
        assert response.json() == {
            "error_code": "SERVICE_UNAVAILABLE",
            "detail": "Required service is temporarily unavailable",
        }

    async def test_does_not_leak_detail(self, exception_client: AsyncClient):
        response = await exception_client.get("/redis-error")

        assert "AUTH failed" not in response.text
        assert "wrong password" not in response.text

    async def test_failure_is_logged(
        self, exception_client: AsyncClient, captured_logs
    ):
        await exception_client.get("/redis-error")

        events = [e for e in captured_logs if e["event"] == "redis_critical_failure"]

        assert len(events) == 1
        assert events[0]["path"] == "/redis-error"
