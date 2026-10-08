import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError
from structlog.testing import capture_logs

from src.core.caching import (
    close_redis,
    delete_cache,
    get_cache,
    get_cache_critical,
    get_redis,
    init_redis,
    set_cache,
    set_cache_critical,
)

REDIS_ERRORS = [RedisError, RedisConnectionError, RedisTimeoutError]
DEFAULT_TTL = 300  # contract: optional cache entries expire after 5 minutes


def make_redis(
    get_return=None,
    get_side_effect=None,
    set_side_effect=None,
    delete_side_effect=None,
) -> AsyncMock:
    """Return an AsyncMock Redis client with configurable behaviour."""

    client = AsyncMock()
    client.get = AsyncMock(return_value=get_return, side_effect=get_side_effect)
    client.set = AsyncMock(return_value=True, side_effect=set_side_effect)
    client.delete = AsyncMock(return_value=1, side_effect=delete_side_effect)

    return client


def events(logs: list[dict]) -> list[str]:
    return [entry["event"] for entry in logs]


class TestGetCache:
    async def test_deserializes_dict(self):
        redis = make_redis(get_return='{"user_id": 123, "role": "teacher"}')

        assert await get_cache(redis, "my-key") == {"user_id": 123, "role": "teacher"}

    async def test_returns_value_on_hit(self):
        redis = make_redis(get_return='"cached_value"')

        assert await get_cache(redis, "my-key") == "cached_value"

    async def test_returns_none_on_miss(self):
        redis = make_redis(get_return=None)

        assert await get_cache(redis, "missing-key") is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("0", 0), ("false", False), ("[]", []), ('""', "")],
    )
    async def test_falsy_cached_values_are_hits_not_misses(self, raw, expected):
        result = await get_cache(make_redis(get_return=raw), "k")

        assert result == expected
        assert type(result) is type(expected)

    async def test_calls_redis_with_correct_key(self):
        redis = make_redis()

        await get_cache(redis, "specific-key")

        redis.get.assert_called_once_with("specific-key")

    @pytest.mark.parametrize("error", REDIS_ERRORS)
    async def test_redis_error_returns_none_and_logs(self, error):
        redis = make_redis(get_side_effect=error("boom"))

        with capture_logs() as logs:
            result = await get_cache(redis, "my-key")

        assert result is None
        assert events(logs) == ["redis_cache_get_failed"]
        assert logs[0]["key"] == "my-key"

    @pytest.mark.parametrize("raw", ["not json", "{broken", "<html>"])
    async def test_corrupt_value_is_a_miss_not_an_error(self, raw):
        redis = make_redis(get_return=raw)

        with capture_logs() as logs:
            result = await get_cache(redis, "my-key")

        assert result is None
        assert events(logs) == ["redis_cache_value_invalid"]


class TestSetCache:
    async def test_serializes_dict(self):
        redis = make_redis()

        await set_cache(redis, "my-key", {"user_id": 123, "role": "teacher"})

        key, stored = redis.set.call_args.args

        assert key == "my-key"
        assert json.loads(stored) == {"user_id": 123, "role": "teacher"}

    async def test_default_ttl_is_applied(self):
        redis = make_redis()

        await set_cache(redis, "my-key", "my-value")

        redis.set.assert_called_once_with("my-key", '"my-value"', ex=DEFAULT_TTL)

    async def test_explicit_ttl_overrides_default(self):
        redis = make_redis()

        await set_cache(redis, "my-key", "my-value", ex=60)

        redis.set.assert_called_once_with("my-key", '"my-value"', ex=60)

    async def test_explicit_none_means_no_expiry(self):
        redis = make_redis()

        await set_cache(redis, "my-key", "my-value", ex=None)

        redis.set.assert_called_once_with("my-key", '"my-value"', ex=None)

    @pytest.mark.parametrize("error", REDIS_ERRORS)
    async def test_redis_error_is_swallowed_and_logged(self, error):
        redis = make_redis(set_side_effect=error("write failed"))

        with capture_logs() as logs:
            await set_cache(redis, "my-key", "my-value")

        redis.set.assert_awaited_once()
        assert events(logs) == ["redis_cache_set_failed"]

    async def test_non_serializable_value_raises_and_skips_redis(self):
        redis = make_redis()

        with pytest.raises(TypeError):
            await set_cache(redis, "my-key", {"obj": object()})

        redis.set.assert_not_called()


class TestDeleteCache:
    async def test_deletes_single_key(self):
        redis = make_redis()

        await delete_cache(redis, "my-key")

        redis.delete.assert_called_once_with("my-key")

    async def test_deletes_multiple_keys_in_one_call(self):
        redis = make_redis()

        await delete_cache(redis, "a", "b", "c")

        redis.delete.assert_called_once_with("a", "b", "c")

    async def test_no_keys_makes_no_redis_call(self):
        redis = make_redis()

        await delete_cache(redis)

        redis.delete.assert_not_called()

    @pytest.mark.parametrize("error", REDIS_ERRORS)
    async def test_redis_error_is_swallowed_and_logged(self, error):
        redis = make_redis(delete_side_effect=error("delete failed"))

        with capture_logs() as logs:
            await delete_cache(redis, "a", "b")

        redis.delete.assert_awaited_once()
        assert events(logs) == ["redis_cache_delete_failed"]
        assert logs[0]["keys"] == ["a", "b"]


class TestCriticalWrappers:
    async def test_get_returns_raw_value(self):
        redis = make_redis(get_return="important_value")

        assert await get_cache_critical(redis, "k") == "important_value"

    async def test_get_calls_redis_with_correct_key(self):
        redis = make_redis()

        await get_cache_critical(redis, "specific-critical-key")

        redis.get.assert_called_once_with("specific-critical-key")

    async def test_get_does_not_json_decode(self):
        redis = make_redis(get_return="not json")

        assert await get_cache_critical(redis, "k") == "not json"

    @pytest.mark.parametrize("error", REDIS_ERRORS)
    async def test_get_propagates_redis_error(self, error):
        redis = make_redis(get_side_effect=error("boom"))

        with pytest.raises(error):
            await get_cache_critical(redis, "k")

    async def test_set_stores_raw_value_with_no_default_ttl(self):
        redis = make_redis()

        await set_cache_critical(redis, "k", "value")

        redis.set.assert_called_once_with("k", "value", ex=None)

    async def test_set_passes_ttl(self):
        redis = make_redis()

        await set_cache_critical(redis, "k", "value", ex=60)

        redis.set.assert_called_once_with("k", "value", ex=60)

    @pytest.mark.parametrize("error", REDIS_ERRORS)
    async def test_set_propagates_redis_error(self, error):
        redis = make_redis(set_side_effect=error("write failed"))

        with pytest.raises(error):
            await set_cache_critical(redis, "k", "value")


def make_app() -> FastAPI:
    app = FastAPI()
    app.state.settings = SimpleNamespace(
        REDIS_URL="redis://:s3cret-pw@redis.example.com:6379/1",
        REDIS_HOST="redis.example.com",
        REDIS_PORT=6379,
        REDIS_DB=1,
    )

    return app


class TestInitRedis:
    async def test_success_stores_client_on_app_state(self):
        app = make_app()
        client = AsyncMock()

        with patch("src.core.caching.aioredis.from_url", return_value=client):
            await init_redis(app)

        client.ping.assert_awaited_once()
        assert app.state.redis is client

    async def test_client_is_created_with_timeouts(self):
        app = make_app()

        with patch(
            "src.core.caching.aioredis.from_url", return_value=AsyncMock()
        ) as from_url:
            await init_redis(app)

        kwargs = from_url.call_args.kwargs

        assert kwargs["socket_connect_timeout"] > 0
        assert kwargs["socket_timeout"] > 0
        assert kwargs["health_check_interval"] > 0

    async def test_failed_ping_closes_client_and_reraises(self):
        app = make_app()
        client = AsyncMock()
        client.ping.side_effect = RedisConnectionError("refused")

        with (
            patch("src.core.caching.aioredis.from_url", return_value=client),
            pytest.raises(RedisConnectionError),
        ):
            await init_redis(app)

        client.aclose.assert_awaited_once()
        assert not hasattr(app.state, "redis")

    async def test_log_has_no_url_and_never_contains_password(self):
        app = make_app()

        with (
            patch("src.core.caching.aioredis.from_url", return_value=AsyncMock()),
            capture_logs() as logs,
        ):
            await init_redis(app)

        connected = [e for e in logs if e["event"] == "redis_connected"]

        assert len(connected) == 1
        assert "url" not in connected[0]
        assert connected[0]["host"] == "redis.example.com"
        assert connected[0]["db"] == 1
        assert "s3cret-pw" not in str(logs)


class TestCloseRedis:
    async def test_closes_client_when_present(self):
        app = make_app()
        app.state.redis = AsyncMock()

        await close_redis(app)

        app.state.redis.aclose.assert_awaited_once()

    async def test_is_a_noop_when_client_was_never_created(self):
        app = make_app()

        await close_redis(app)  # must not raise


class TestGetRedis:
    def test_returns_client_stored_on_app_state(self):
        app = FastAPI()
        client = object()
        app.state.redis = client
        request = Request({"type": "http", "app": app})

        assert get_redis(request) is client


class TestCacheRoundTrip:
    async def test_value_survives_real_redis_with_default_ttl(
        self, redis_client: Redis
    ):
        payload = {"user_id": 123, "role": "teacher", "tags": ["a", "b"], "n": None}

        await set_cache(redis_client, "roundtrip-key", payload)

        assert await get_cache(redis_client, "roundtrip-key") == payload
        assert 0 < await redis_client.ttl("roundtrip-key") <= 300
