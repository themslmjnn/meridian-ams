import jwt
import pytest
from fastapi import APIRouter, FastAPI, Request, Response
from httpx import ASGITransport, AsyncClient

from meridian_ams.core.limiter import get_user_identifier, limiter

router = APIRouter()


@router.get("/test/ip")
@limiter.limit("2/minute")
async def limited_ip_endpoint(request: Request, response: Response):
    return {"message": "ok"}


@router.get("/test/user")
@limiter.limit("2/minute", key_func=get_user_identifier)
async def limited_user_endpoint(
    request: Request,
    response: Response,
):
    return {"message": "ok"}


@pytest.fixture
def fake_token_decoding(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_decode(token: str) -> dict:
        if token == "no-sub":
            return {}

        if token.startswith("valid-"):
            return {"sub": token.removeprefix("valid-")}

        raise jwt.InvalidTokenError("Invalid token")

    monkeypatch.setattr(
        "meridian_ams.core.limiter.decode_access_token",
        fake_decode,
    )


@pytest.fixture
def limiter_app(app: FastAPI) -> FastAPI:
    app.include_router(router)
    return app


@pytest.fixture
async def limiter_client(limiter_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=limiter_app),
        base_url="http://localhost",
    ) as client:
        yield client


class TestGetUserIdentifier:
    def test_valid_token_returns_user_id(
        self,
        fake_token_decoding: None,
    ) -> None:
        request = Request(
            {
                "type": "http",
                "headers": [(b"authorization", b"Bearer valid-alice")],
                "client": ("203.0.113.7", 5000),
            }
        )

        assert get_user_identifier(request) == "user:alice"

    @pytest.mark.parametrize(
        "authorization",
        [
            None,
            "Bearer invalid-token",
            "Bearer no-sub",
        ],
    )
    def test_missing_or_invalid_token_returns_ip(
        self,
        fake_token_decoding: None,
        authorization: str | None,
    ) -> None:
        headers = []

        if authorization:
            headers.append((b"authorization", authorization.encode()))

        request = Request(
            {
                "type": "http",
                "headers": headers,
                "client": ("203.0.113.7", 5000),
            }
        )

        assert get_user_identifier(request) == "203.0.113.7"


class TestRateLimiting:
    async def test_ip_limiter_returns_429_after_limit(
        self,
        limiter_client: AsyncClient,
    ) -> None:
        first = await limiter_client.get("/test/ip")
        second = await limiter_client.get("/test/ip")
        third = await limiter_client.get("/test/ip")

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
        assert third.json() == {
            "error_code": "RATE_LIMIT_EXCEEDED",
            "detail": "Too many requests.",
        }

    async def test_user_limiter_uses_separate_user_buckets(
        self,
        limiter_client: AsyncClient,
        fake_token_decoding: None,
    ) -> None:
        alice_headers = {"Authorization": "Bearer valid-alice"}
        bob_headers = {"Authorization": "Bearer valid-bob"}

        alice_first = await limiter_client.get(
            "/test/user",
            headers=alice_headers,
        )
        alice_second = await limiter_client.get(
            "/test/user",
            headers=alice_headers,
        )
        alice_third = await limiter_client.get(
            "/test/user",
            headers=alice_headers,
        )
        bob_first = await limiter_client.get(
            "/test/user",
            headers=bob_headers,
        )

        assert alice_first.status_code == 200
        assert alice_second.status_code == 200
        assert alice_third.status_code == 429
        assert bob_first.status_code == 200
