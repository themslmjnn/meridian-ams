import json
from typing import Any

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = structlog.get_logger(__name__)

DEFAULT_CACHE_TTL_SECONDS = 300


async def get_cache(redis: Redis, key: str) -> Any | None:
    try:
        cached_value = await redis.get(key)

    except RedisError as exc:
        logger.warning(
            "redis_get_cache_failed",
            key=key,
            error=repr(exc),
        )

        return None

    if cached_value is None:
        return None

    try:
        return json.loads(cached_value)

    except ValueError:
        logger.warning(
            "redis_get_cache_failed",
            key=key,
            failure_reason="invalid_cache_value",
        )

        return None


async def set_cache(
    redis: Redis,
    key: str,
    value: Any,
    ttl: int = DEFAULT_CACHE_TTL_SECONDS,
) -> None:
    if value is None:
        return

    payload = json.dumps(value)

    try:
        await redis.set(key, payload, ex=ttl)

    except RedisError as exc:
        logger.warning(
            "redis_set_cache_failed",
            key=key,
            error=repr(exc),
        )


async def delete_cache(redis: Redis, *keys: str) -> None:
    if not keys:
        return

    try:
        await redis.delete(*keys)

    except RedisError as exc:
        logger.warning(
            "redis_delete_cache_failed",
            keys=list(keys),
            error=repr(exc),
        )


async def delete_cache_critical(redis: Redis, *keys: str) -> None:
    if not keys:
        return

    await redis.delete(*keys)
