from typing import Any

from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from meridian_ams.core.config import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    pool_kwargs: dict[str, Any] = (
        {"poolclass": NullPool}
        if settings.ENVIRONMENT == "test"
        else {
            "pool_timeout": settings.DB_POOL_TIMEOUT,
        }
    )

    return create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, **pool_kwargs)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
