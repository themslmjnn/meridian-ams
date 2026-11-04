from meridian_ams.core.config import Settings
from meridian_ams.core.redis.client import (
    SOCKET_CONNECT_TIMEOUT_SECONDS,
    SOCKET_TIMEOUT_SECONDS,
    build_redis,
)


async def test_build_redis_applies_settings(settings: Settings) -> None:
    client = build_redis(settings)

    try:
        kwargs = client.connection_pool.connection_kwargs

        assert kwargs["decode_responses"] is True
        assert kwargs["socket_connect_timeout"] == SOCKET_CONNECT_TIMEOUT_SECONDS
        assert kwargs["socket_timeout"] == SOCKET_TIMEOUT_SECONDS
    finally:
        await client.aclose()
