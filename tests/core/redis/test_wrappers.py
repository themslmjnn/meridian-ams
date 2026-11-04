import json
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from meridian_ams.core.redis.wrappers import (
    DEFAULT_CACHE_TTL_SECONDS,
    delete_cache,
    delete_cache_critical,
    get_cache,
    set_cache,
)


class TestGetCache:
    async def test_returns_stored_value(self, redis_client: Redis) -> None:
        value = {"name": "Ali", "count": 3}
        await redis_client.set("k", json.dumps(value))

        assert await get_cache(redis_client, "k") == value

    async def test_returns_none_for_missing_key(self, redis_client: Redis) -> None:
        assert await get_cache(redis_client, "missing") is None

    async def test_returns_none_when_redis_fails(self) -> None:
        redis = AsyncMock()
        redis.get.side_effect = RedisError("down")

        assert await get_cache(redis, "k") is None

    async def test_returns_none_for_corrupt_value(self, redis_client: Redis) -> None:
        await redis_client.set("k", "not json")

        assert await get_cache(redis_client, "k") is None


class TestSetCache:
    async def test_stores_json_with_ttl(self, redis_client: Redis) -> None:
        value = {"name": "Ali"}

        await set_cache(redis_client, "k", value, ttl=DEFAULT_CACHE_TTL_SECONDS)

        assert json.loads(await redis_client.get("k")) == value
        assert 0 < await redis_client.ttl("k") <= DEFAULT_CACHE_TTL_SECONDS

    async def test_skips_none(self, redis_client: Redis) -> None:
        await set_cache(redis_client, "k", None, ttl=DEFAULT_CACHE_TTL_SECONDS)

        assert await redis_client.exists("k") == 0

    async def test_swallows_redis_error(self) -> None:
        redis = AsyncMock()
        redis.set.side_effect = RedisError("down")

        await set_cache(redis, "k", {"a": 1}, ttl=DEFAULT_CACHE_TTL_SECONDS)

    async def test_raises_type_error_for_unserializable_value(self) -> None:
        redis = AsyncMock()

        with pytest.raises(TypeError):
            await set_cache(redis, "k", datetime.now(), ttl=DEFAULT_CACHE_TTL_SECONDS)

        redis.set.assert_not_awaited()


class TestDeleteCache:
    async def test_removes_multiple_keys(self, redis_client: Redis) -> None:
        await redis_client.set("a", "1")
        await redis_client.set("b", "2")

        await delete_cache(redis_client, "a", "b")

        assert await redis_client.exists("a", "b") == 0

    async def test_without_keys_does_not_call_redis(self) -> None:
        redis = AsyncMock()

        await delete_cache(redis)

        redis.delete.assert_not_awaited()

    async def test_swallows_redis_error(self) -> None:
        redis = AsyncMock()
        redis.delete.side_effect = RedisError("down")

        await delete_cache(redis, "a")


class TestDeleteCacheCritical:
    async def test_removes_keys(self, redis_client: Redis) -> None:
        await redis_client.set("a", "1")
        await redis_client.set("b", "2")

        await delete_cache_critical(redis_client, "a", "b")

        assert await redis_client.exists("a", "b") == 0

    async def test_without_keys_does_not_call_redis(self) -> None:
        redis = AsyncMock()

        await delete_cache_critical(redis)

        redis.delete.assert_not_awaited()

    async def test_propagates_redis_error(self) -> None:
        redis = AsyncMock()
        redis.delete.side_effect = RedisError("down")

        with pytest.raises(RedisError):
            await delete_cache_critical(redis, "a")
