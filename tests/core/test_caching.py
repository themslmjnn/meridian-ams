from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError, RedisError, TimeoutError

from src.core.caching import (
    delete_cache,
    get_cache,
    get_cache_critical,
    set_cache,
    set_cache_critical,
)


# Helpers
def make_redis(
    get_return=None,
    set_return=True,
    delete_return=1,
    get_side_effect=None,
    set_side_effect=None,
    delete_side_effect=None,
) -> AsyncMock:
    """Return an AsyncMock Redis client with configurable behaviour."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=get_return, side_effect=get_side_effect)
    client.set = AsyncMock(return_value=set_return, side_effect=set_side_effect)
    client.delete = AsyncMock(
        return_value=delete_return, side_effect=delete_side_effect
    )

    return client


# get_cache — optional wrapper
async def test_get_cache_returns_value_on_hit():
    redis = make_redis(get_return="cached_value")
    result = await get_cache(redis, "my-key")

    assert result == "cached_value"


async def test_get_cache_returns_none_on_miss():
    redis = make_redis(get_return=None)
    result = await get_cache(redis, "missing-key")

    assert result is None


async def test_get_cache_returns_none_on_redis_error():
    """Optional wrapper must swallow RedisError and return None."""
    redis = make_redis(get_side_effect=RedisError("connection lost"))
    result = await get_cache(redis, "my-key")

    assert result is None


async def test_get_cache_returns_none_on_connection_error():
    redis = make_redis(get_side_effect=ConnectionError("refused"))
    result = await get_cache(redis, "my-key")

    assert result is None


async def test_get_cache_returns_none_on_timeout():
    redis = make_redis(get_side_effect=TimeoutError("timed out"))
    result = await get_cache(redis, "my-key")

    assert result is None


async def test_get_cache_calls_redis_with_correct_key():
    redis = make_redis()
    await get_cache(redis, "specific-key")

    redis.get.assert_called_once_with("specific-key")


# set_cache — optional wrapper
async def test_set_cache_calls_redis_set():
    redis = make_redis()
    await set_cache(redis, "my-key", "my-value")

    redis.set.assert_called_once_with("my-key", "my-value", ex=None)


async def test_set_cache_passes_ttl():
    redis = make_redis()
    await set_cache(redis, "my-key", "my-value", ex=300)

    redis.set.assert_called_once_with("my-key", "my-value", ex=300)


async def test_set_cache_swallows_redis_error():
    """Optional wrapper must not raise on RedisError."""
    redis = make_redis(set_side_effect=RedisError("write failed"))
    # Must not raise
    await set_cache(redis, "my-key", "my-value")


async def test_set_cache_swallows_connection_error():
    redis = make_redis(set_side_effect=ConnectionError("refused"))
    await set_cache(redis, "my-key", "my-value")


# delete_cache — optional wrapper
async def test_delete_cache_calls_redis_delete():
    redis = make_redis()
    await delete_cache(redis, "my-key")

    redis.delete.assert_called_once_with("my-key")


async def test_delete_cache_swallows_redis_error():
    redis = make_redis(delete_side_effect=RedisError("delete failed"))
    # Must not raise
    await delete_cache(redis, "my-key")


# get_cache_critical — propagates errors
async def test_get_cache_critical_returns_value():
    redis = make_redis(get_return="important_value")
    result = await get_cache_critical(redis, "critical-key")

    assert result == "important_value"


async def test_get_cache_critical_raises_on_redis_error():
    """Critical wrapper must propagate RedisError — silent failure is a security risk."""
    redis = make_redis(get_side_effect=RedisError("connection lost"))
    with pytest.raises(RedisError):
        await get_cache_critical(redis, "critical-key")


async def test_get_cache_critical_raises_on_connection_error():
    redis = make_redis(get_side_effect=ConnectionError("refused"))
    with pytest.raises(ConnectionError):
        await get_cache_critical(redis, "critical-key")


async def test_get_cache_critical_raises_on_timeout():
    redis = make_redis(get_side_effect=TimeoutError("timed out"))
    with pytest.raises(TimeoutError):
        await get_cache_critical(redis, "critical-key")


async def test_get_cache_critical_calls_redis_with_correct_key():
    redis = make_redis()
    await get_cache_critical(redis, "specific-critical-key")

    redis.get.assert_called_once_with("specific-critical-key")


# set_cache_critical — propagates errors
async def test_set_cache_critical_calls_redis_set():
    redis = make_redis()
    await set_cache_critical(redis, "critical-key", "value")

    redis.set.assert_called_once_with("critical-key", "value", ex=None)


async def test_set_cache_critical_passes_ttl():
    redis = make_redis()
    await set_cache_critical(redis, "critical-key", "value", ex=60)

    redis.set.assert_called_once_with("critical-key", "value", ex=60)


async def test_set_cache_critical_raises_on_redis_error():
    redis = make_redis(set_side_effect=RedisError("write failed"))
    with pytest.raises(RedisError):
        await set_cache_critical(redis, "critical-key", "value")


async def test_set_cache_critical_raises_on_connection_error():
    redis = make_redis(set_side_effect=ConnectionError("refused"))
    with pytest.raises(ConnectionError):
        await set_cache_critical(redis, "critical-key", "value")


# Behavioural contract — optional vs critical
async def test_optional_wrapper_never_raises_redis_error():
    """
    Exhaustive check: all optional wrappers swallow every RedisError subclass.
    A cache failure must never crash a request.
    """
    error = RedisError("any redis error")
    redis_get = make_redis(get_side_effect=error)
    redis_set = make_redis(set_side_effect=error)
    redis_del = make_redis(delete_side_effect=error)

    # None of these should raise
    assert await get_cache(redis_get, "k") is None
    await set_cache(redis_set, "k", "v")
    await delete_cache(redis_del, "k")


async def test_critical_wrappers_always_raise_redis_error():
    """
    Exhaustive check: all critical wrappers propagate every RedisError subclass.
    A security-sensitive operation must never silently fail.
    """
    error = RedisError("any redis error")
    redis_get = make_redis(get_side_effect=error)
    redis_set = make_redis(set_side_effect=error)

    with pytest.raises(RedisError):
        await get_cache_critical(redis_get, "k")

    with pytest.raises(RedisError):
        await set_cache_critical(redis_set, "k", "v")
