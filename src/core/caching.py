import json
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.core.config import get_settings

logger = structlog.get_logger(__name__)

settings = get_settings()


async def init_redis(app: "FastAPI") -> None:
    """
    Create the Redis client, verify connectivity, and store on app.state.

    Called during lifespan startup. Raises if Redis is unreachable — we want
    to fail fast on startup rather than discover it on the first request.
    """

    client = aioredis.from_url(
        app.state.settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )

    await client.ping()

    app.state.redis = client

    logger.info("redis_connected", url=app.state.settings.REDIS_URL)


async def close_redis(app: "FastAPI") -> None:
    """
    Close the Redis client during lifespan shutdown.

    Must be called explicitly to avoid ResourceWarning in tests.
    """

    if hasattr(app.state, "redis"):
        await app.state.redis.aclose()

        logger.info("redis_closed")


def get_redis(request: Request) -> Redis:
    """FastAPI dependency returning the shared Redis client."""

    return request.app.state.redis  # type: ignore[no-any-return]


# Optional wrappers — cache operations
# These swallow RedisError and return None.
# A cache miss is not an error; the app falls back to the DB.
async def get_cache(redis: Redis, key: str) -> str | None:
    try:
        value = await redis.get(key)
        if value is None:
            return None

        return json.loads(value)  # type: ignore[no-any-return]

    except RedisError as exc:
        logger.warning("redis_cache_get_failed", key=key, error=str(exc))


async def set_cache(
    redis: Redis,
    key: str,
    value: str,
    ex: int | None = None,
) -> None:
    try:
        await redis.set(key, json.dumps(value), ex=ex)

    except RedisError as exc:
        logger.warning("redis_cache_set_failed", key=key, error=str(exc))


async def delete_cache(redis: Redis, *keys: str) -> None:
    try:
        await redis.delete(*keys)

    except RedisError as exc:
        logger.warning("redis_cache_delete_failed", key=keys, error=str(exc))


# Critical wrappers — security-sensitive operations
# These propagate RedisError. Rate limiting and token version checks use these.
# A silent failure here is a security failure.
async def get_cache_critical(redis: Redis, key: str) -> Any:
    return await redis.get(key)


async def set_cache_critical(
    redis: Redis,
    key: str,
    value: str,
    ex: int | None = None,
) -> None:
    await redis.set(key, value, ex=ex)
