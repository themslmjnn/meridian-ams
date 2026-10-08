import json
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = structlog.get_logger(__name__)

# Bound Redis I/O so a hung server fails fast instead of stalling requests.
_SOCKET_CONNECT_TIMEOUT = 2
_SOCKET_TIMEOUT = 2
_HEALTH_CHECK_INTERVAL = 30
_DEFAULT_CACHE_TTL = 300


async def init_redis(app: FastAPI) -> None:
    """
    Create the Redis client, verify connectivity, and store on app.state.

    Called during lifespan startup. Raises if Redis is unreachable — we want
    to fail fast on startup rather than discover it on the first request.
    """

    settings = app.state.settings

    client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=_SOCKET_CONNECT_TIMEOUT,
        socket_timeout=_SOCKET_TIMEOUT,
        health_check_interval=_HEALTH_CHECK_INTERVAL,
    )

    try:
        await client.ping()

    except BaseException:
        await client.aclose()
        raise

    app.state.redis = client

    # Never log REDIS_URL: it contains the password.
    logger.info(
        "redis_connected",
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
    )


async def close_redis(app: FastAPI) -> None:
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
# These swallow RedisError and treat it as a miss / no-op.
# A cache miss is not an error; the app falls back to the DB.
async def get_cache(redis: Redis, key: str) -> Any | None:
    try:
        value = await redis.get(key)

    except RedisError as exc:
        logger.warning("redis_cache_get_failed", key=key, error=str(exc))

        return None

    if value is None:
        return None

    try:
        return json.loads(value)

    except ValueError:
        # Corrupt or stale-format entry: treat as a miss, never fail the request.
        logger.warning("redis_cache_value_invalid", key=key)

        return None


async def set_cache(
    redis: Redis,
    key: str,
    value: Any,
    ex: int | None = _DEFAULT_CACHE_TTL,
) -> None:
    try:
        await redis.set(key, json.dumps(value), ex=ex)

    except RedisError as exc:
        logger.warning("redis_cache_set_failed", key=key, error=str(exc))


async def delete_cache(redis: Redis, *keys: str) -> None:
    if not keys:
        return

    try:
        await redis.delete(*keys)

    except RedisError as exc:
        logger.warning("redis_cache_delete_failed", keys=list(keys), error=str(exc))


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
