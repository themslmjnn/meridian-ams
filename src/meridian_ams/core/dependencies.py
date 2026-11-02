from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.async_session_factory() as db_session:
        yield db_session


def get_redis(request: Request) -> Redis:
    return cast("Redis", request.app.state.redis)


db_session_dependency = Annotated[AsyncSession, Depends(get_db_session)]
redis_dependency = Annotated[Redis, Depends(get_redis)]
