import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import Header, Response, status
from fastapi.responses import JSONResponse
from redis import RedisError
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.core.advisory_locks import NAMESPACE_IDEMPOTENCY, compute_lock_key
from meridian_ams.core.config import get_settings
from meridian_ams.core.idempotency.repository import IdempotencyRepository
from meridian_ams.core.idempotency.utils.exceptions import (
    CachedResponseSignal,
    IdempotencyPayloadMismatch,
    IdempotencyRequestInProgress,
)
from meridian_ams.database.errors import is_lock_timeout
from meridian_ams.utils.cache_keys import IdempotencyCacheKey

logger = structlog.get_logger(__name__)

IDEMPOTENCY_KEY_HEADER = Header(
    alias="Idempotency-Key",
    description=(
        "Client-generated UUID. Attach before the first attempt and reuse on every retry."
        "The server returns the original response without re-executing the operation if the key is already complete."
    ),
)


def hash_payload(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    return hashlib.sha256(canonical.encode()).hexdigest()


def make_idempotency_key_dependency():
    """
    Factory for an endpoint-scoped idempotency key dependency.

    Validates that the Idempotency-Key header is a valid UUID.
    Returns it as a string for use in the use case layer.

    This dependency only extracts the key — it does not perform idempotency.
    The actual idempotency logic lives in acquire_idempotency_lock
    called from the use case.
    """

    async def idempotency_key_dependency(
        idempotency_key: uuid.UUID = IDEMPOTENCY_KEY_HEADER,
    ) -> str:
        return str(idempotency_key)

    return idempotency_key_dependency


async def acquire_idempotency_lock(
    db_session: AsyncSession,
    redis: Redis,
    *,
    actor_id: int,
    operation: str,
    idempotency_key: str,
    payload_hash: str,
) -> None:
    """
    Serialize same-key requests and replay a stored result if one exists.

    Returns normally only when the caller should execute the operation; the
    advisory lock is then held until the caller commits or rolls back.
    Raises CachedResponseSignal for a replay, IdempotencyPayloadMismatch for a
    reused key with a different payload, IdempotencyRequestInProgress when the
    lock wait times out.
    """
    cache_key = IdempotencyCacheKey.idempotency_key(
        operation, actor_id, idempotency_key
    )

    cached_value = await _safe_redis_get(redis, cache_key)
    if cached_value is not None:
        if cached_value["request_hash"] != payload_hash:
            raise IdempotencyPayloadMismatch()

        raise CachedResponseSignal(cached_value["http_status"], cached_value["body"])

    await _take_key_lock(db_session, operation, actor_id, idempotency_key)

    await IdempotencyRepository.delete_expired(
        db_session,
        operation=operation,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )

    existing = await IdempotencyRepository.get_record(
        db_session,
        operation=operation,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    if existing is None:
        return

    if existing.request_hash != payload_hash:
        raise IdempotencyPayloadMismatch()

    await mirror_complete_to_redis(
        redis,
        actor_id=actor_id,
        operation=operation,
        idempotency_key=idempotency_key,
        payload_hash=existing.request_hash,
        http_status=existing.http_status,
        body=existing.response_body,
        expires_at=existing.expires_at,
    )

    raise CachedResponseSignal(existing.http_status, existing.response_body)


async def store_idempotency_record(
    db_session: AsyncSession,
    *,
    actor_id: int,
    operation: str,
    idempotency_key: str,
    payload_hash: str,
    http_status: int,
    body: dict | list | None,
) -> datetime:
    """Insert the completed record inside the caller's transaction. No commit."""
    expires_at = datetime.now(UTC) + timedelta(
        seconds=get_settings().IDEMPOTENCY_KEY_TTL
    )

    await IdempotencyRepository.add_record(
        db_session,
        operation=operation,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        http_status=http_status,
        body=body,
        expires_at=expires_at,
    )

    return expires_at


async def mirror_complete_to_redis(
    redis: Redis,
    *,
    actor_id: int,
    operation: str,
    idempotency_key: str,
    payload_hash: str,
    http_status: int,
    body: dict | list | None,
    expires_at: datetime,
) -> None:
    """Best-effort Redis mirror. Never raises. TTL is the record's remaining life."""

    ttl = int((expires_at - datetime.now(UTC)).total_seconds())
    if ttl <= 0:
        return

    cache_key = IdempotencyCacheKey.idempotency_key(
        operation, actor_id, idempotency_key
    )

    try:
        await redis.set(
            cache_key,
            json.dumps(
                {
                    "status": "complete",
                    "request_hash": payload_hash,
                    "http_status": http_status,
                    "body": body,
                }
            ),
            ex=ttl,
        )

    except RedisError as exc:
        logger.warning(
            "idempotency_redis_mirror_failed",
            operation=operation,
            actor_id=actor_id,
            error=type(exc).__name__,
        )


async def _take_key_lock(db_session, operation, actor_id, idempotency_key) -> None:
    settings = get_settings()

    try:
        await db_session.execute(
            text("SELECT set_config('lock_timeout', :ms, true)"),
            {"ms": str(settings.IDEMPOTENCY_LOCK_TIMEOUT_MS)},
        )

        await db_session.execute(
            text("SELECT pg_advisory_xact_lock(:ns, :key)"),
            {
                "ns": NAMESPACE_IDEMPOTENCY,
                "key": compute_lock_key(f"{operation}:{actor_id}:{idempotency_key}"),
            },
        )

    except DBAPIError as exc:
        if is_lock_timeout(exc):
            await db_session.rollback()

            raise IdempotencyRequestInProgress() from exc

        raise


async def _safe_redis_get(redis: Redis, cache_key: str) -> dict | None:
    """Redis read failure or a malformed entry means a cache miss. The DB decides."""
    try:
        cached_value = await redis.get(cache_key)

    except RedisError as exc:
        logger.warning("idempotency_redis_read_failed", error=type(exc).__name__)

        return None

    if cached_value is None:
        return None

    try:
        data = json.loads(cached_value)

    except ValueError:
        logger.warning("idempotency_cache_entry_corrupt")

        return None

    if (
        not isinstance(data, dict)
        or data.get("status") != "complete"
        or not {"request_hash", "http_status", "body"} <= data.keys()
    ):
        return None

    return data


def make_cached_response(signal: CachedResponseSignal) -> JSONResponse:
    """Convert a _CachedResponseSignal into a JSONResponse."""

    if signal.status_code == status.HTTP_204_NO_CONTENT:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return JSONResponse(status_code=signal.status_code, content=signal.body)
