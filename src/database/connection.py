from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from src.core.config import get_settings

settings = get_settings()

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

_engine_kwargs: dict[str, Any] = {
    "url": settings.DATABASE_URL,
    "pool_pre_ping": True,
    "echo": False,
    "connect_args": {
        "timeout": settings.DB_CONNECT_TIMEOUT,
        "server_settings": {
            "statement_timeout": str(settings.DB_STATEMENT_TIMEOUT_MS),
            "idle_in_transaction_session_timeout": str(
                settings.DB_IDLE_IN_TX_TIMEOUT_MS
            ),
            "application_name": settings.APP_NAME,
        },
    },
}

if settings.ENVIRONMENT == "test":
    # Pooled asyncpg connections cannot be shared across per-test event loops.
    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs.update(
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
    )

engine: AsyncEngine = create_async_engine(**_engine_kwargs)

session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class ImmutableBase(DeclarativeBase):
    __abstract__ = True

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    id: Mapped[int] = mapped_column(primary_key=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MutableBase(ImmutableBase):
    __abstract__ = True

    # Fetch server-side defaults (incl. onupdate) via RETURNING on INSERT and
    # UPDATE so updated_at is never left expired in async sessions.
    __mapper_args__ = {"eager_defaults": True}

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


async def dispose_engine() -> None:
    """Dispose the engine connection pool. Called during lifespan shutdown."""

    await engine.dispose()
