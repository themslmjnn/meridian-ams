import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, field_validator
from redis.exceptions import RedisError

from meridian_ams.core.exceptions import AppException, register_exception_handlers


class ThingNotFoundError(AppException):
    status_code = 404
    error_code = "THING_NOT_FOUND"
    detail = "Thing not found"


class Item(BaseModel):
    number: int

    @field_validator("number")
    @classmethod
    def must_be_even(cls, value: int) -> int:
        if value % 2:
            raise ValueError("must be even")

        return value


@pytest.fixture
def error_app() -> FastAPI:
    app = FastAPI()

    register_exception_handlers(app)

    @app.get("/app-error")
    async def app_error() -> None:
        raise ThingNotFoundError

    @app.get("/app-error-custom")
    async def app_error_custom() -> None:
        raise ThingNotFoundError("Thing 5 not found")

    @app.get("/query")
    async def query(limit: int) -> dict:
        return {"limit": limit}

    @app.post("/items")
    async def create_item(item: Item) -> dict:
        return {"number": item.number}

    @app.get("/redis-failure")
    async def redis_failure() -> None:
        raise RedisError("password=hunter2")

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("secret internal detail")

    return app


@pytest_asyncio.fixture
async def client(error_app: FastAPI):
    transport = ASGITransport(app=error_app, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestAppException:
    def test_defaults(self):
        exc = AppException()

        assert exc.status_code == 500
        assert exc.error_code == "INTERNAL_ERROR"
        assert exc.detail == "Internal server error"

    def test_detail_override_applies_to_that_instance_only(self):
        exc = ThingNotFoundError("Thing 5 not found")

        assert exc.detail == "Thing 5 not found"
        assert str(exc) == "Thing 5 not found"
        assert ThingNotFoundError().detail == "Thing not found"


class TestHandlers:
    async def test_app_exception_uses_its_own_status_and_body(
        self, client: AsyncClient
    ):
        response = await client.get("/app-error")

        assert response.status_code == 404
        assert response.json() == {
            "error_code": "THING_NOT_FOUND",
            "detail": "Thing not found",
        }

    async def test_app_exception_with_custom_detail(self, client: AsyncClient):
        response = await client.get("/app-error-custom")

        assert response.status_code == 404
        assert response.json()["detail"] == "Thing 5 not found"

    async def test_validation_error_has_the_standard_shape(self, client: AsyncClient):
        response = await client.get("/query", params={"limit": "abc"})

        body = response.json()

        assert response.status_code == 422
        assert body["error_code"] == "VALIDATION_ERROR"
        assert body["detail"] == "Request validation failed"
        assert len(body["errors"]) == 1
        assert set(body["errors"][0]) == {"field", "message", "type"}
        assert body["errors"][0]["field"] == "query -> limit"
        assert body["errors"][0]["type"] == "int_parsing"

    async def test_validation_message_drops_the_value_error_prefix(
        self, client: AsyncClient
    ):
        response = await client.post("/items", json={"number": 3})

        error = response.json()["errors"][0]

        assert error["field"] == "body -> number"
        assert error["message"] == "must be even"

    async def test_unknown_route_uses_the_standard_shape(self, client: AsyncClient):
        response = await client.get("/does-not-exist")

        assert response.status_code == 404
        assert response.json() == {"error_code": "HTTP_ERROR", "detail": "Not Found"}

    async def test_wrong_method_keeps_the_allow_header(self, client: AsyncClient):
        response = await client.post("/app-error")

        assert response.status_code == 405
        assert response.json()["error_code"] == "HTTP_ERROR"
        assert "GET" in response.headers["allow"]

    async def test_redis_error_becomes_503_without_leaking_details(
        self, client: AsyncClient
    ):
        response = await client.get("/redis-failure")

        assert response.status_code == 503
        assert response.json() == {
            "error_code": "SERVICE_UNAVAILABLE",
            "detail": "Required service is temporarily unavailable",
        }
        assert "hunter2" not in response.text

    async def test_unhandled_exception_becomes_500_without_leaking_details(
        self, client: AsyncClient
    ):
        response = await client.get("/crash")

        assert response.status_code == 500
        assert response.json() == {
            "error_code": "INTERNAL_ERROR",
            "detail": "Internal server error",
        }
        assert "secret" not in response.text
