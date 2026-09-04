import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from redis.exceptions import RedisError

from src.main import app
from src.users.utils.exceptions import DuplicateEmailError, UserNotFoundError
from src.utils.exceptions import AccessDeniedError


@pytest_asyncio.fixture(scope="function")
async def exception_client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as async_client:
        yield async_client


class StrictBody(BaseModel):
    name: str
    age: int


class TestAppExceptionHandler:
    async def test_app_exception_returns_correct_shape(self, unit_client: AsyncClient):
        """AppException must produce the standard error JSON shape."""

        @app.get("/test/app-exception")
        async def _():
            raise UserNotFoundError()

        response = await unit_client.get("/test/app-exception")

        assert response.status_code == 404
        body = response.json()
        assert body["error_code"] == "USER_NOT_FOUND"
        assert body["detail"] == "User not found"

    async def test_app_exception_status_code_is_respected(
        self, unit_client: AsyncClient
    ):
        """Each AppException status code must be preserved in the HTTP response."""

        @app.get("/test/conflict")
        async def _():
            raise DuplicateEmailError()

        response = await unit_client.get("/test/conflict")

        assert response.status_code == 409
        assert response.json()["error_code"] == "DUPLICATE_EMAIL"

    async def test_app_exception_403(self, unit_client: AsyncClient):
        @app.get("/test/forbidden")
        async def _():
            raise AccessDeniedError()

        response = await unit_client.get("/test/forbidden")

        assert response.status_code == 403
        body = response.json()
        assert body["error_code"] == "ACCESS_DENIED"
        assert "error_code" in body
        assert "detail" in body
        # Must not contain any extra keys
        assert set(body.keys()) == {"error_code", "detail"}

    async def test_app_exception_body_has_exactly_two_keys(
        self, unit_client: AsyncClient
    ):
        """The error body must contain exactly error_code and detail — nothing else."""

        @app.get("/test/shape-check")
        async def _():
            raise UserNotFoundError()

        response = await unit_client.get("/test/shape-check")

        assert set(response.json().keys()) == {"error_code", "detail"}


class TestValidationErrorHandler:
    async def test_validation_error_returns_422_shape(self, unit_client):
        """RequestValidationError must produce a normalised 422 JSON shape."""

        @app.post("/test/validation")
        async def _(body: StrictBody):
            return body

        response = await unit_client.post(
            "/test/validation", json={"name": "Alice", "age": "not-an-int"}
        )

        assert response.status_code == 422
        body = response.json()
        assert body["error_code"] == "VALIDATION_ERROR"
        assert "errors" in body
        assert isinstance(body["errors"], list)
        assert len(body["errors"]) > 0

    async def test_validation_error_each_error_has_required_keys(
        self, unit_client: AsyncClient
    ):
        """Each error object must have field, message, and type keys."""

        @app.post("/test/validation-keys")
        async def _(body: StrictBody):
            return body

        response = await unit_client.post(
            "/test/validation-keys", json={"name": "Alice", "age": "bad"}
        )

        error = response.json()["errors"][0]
        assert "field" in error
        assert "message" in error
        assert "type" in error

    async def test_validation_error_missing_required_field(
        self, unit_client: AsyncClient
    ):
        """Missing required field must be reported as a validation error."""

        @app.post("/test/validation-missing")
        async def _(body: StrictBody):
            return body

        # age is missing entirely
        response = await unit_client.post(
            "/test/validation-missing", json={"name": "Alice"}
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "VALIDATION_ERROR"


class TestUnhandledExceptionHandler:
    async def test_unhandled_exception_returns_500(self, unit_client: AsyncClient):
        @app.get("/test/unhandled")
        async def _():
            raise RuntimeError("secret internal error message")

        response = await unit_client.get("/test/unhandled")

        assert response.status_code == 500

    async def test_unhandled_exception_does_not_leak_detail(
        self, unit_client: AsyncClient
    ):
        """Internal error messages must never appear in the response body."""

        @app.get("/test/unhandled-leak")
        async def _():
            raise RuntimeError("secret internal error message")

        response = await unit_client.get("/test/unhandled-leak")

        body = response.json()
        assert body["error_code"] == "INTERNAL_SERVER_ERROR"
        assert "secret internal error message" not in str(body)
        assert "RuntimeError" not in str(body)

    async def test_unhandled_exception_body_shape(self, unit_client: AsyncClient):
        """500 response must use the standard error shape."""

        @app.get("/test/unhandled-shape")
        async def _():
            raise ValueError("oops")

        response = await unit_client.get("/test/unhandled-shape")

        body = response.json()
        assert "error_code" in body
        assert "detail" in body


class TestRedisErrorHandler:
    async def test_redis_error_returns_503(self, unit_client: AsyncClient):
        """RedisError from a critical operation must return 503."""

        @app.get("/test/redis-error")
        async def _():
            raise RedisError("connection refused")

        response = await unit_client.get("/test/redis-error")

        assert response.status_code == 503
        body = response.json()
        assert body["error_code"] == "SERVICE_UNAVAILABLE"

    async def test_redis_error_does_not_leak_detail(self, unit_client: AsyncClient):
        """503 response must not expose internal Redis error messages."""

        @app.get("/test/redis-leak")
        async def _():
            raise RedisError("AUTH failed: wrong password")

        response = await unit_client.get("/test/redis-leak")

        body = response.json()
        assert "AUTH failed" not in str(body)
        assert "wrong password" not in str(body)
