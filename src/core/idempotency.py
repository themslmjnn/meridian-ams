import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import Header
from fastapi.responses import JSONResponse
from redis import RedisError
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.models import IdempotencyRecord
from src.utils.cache_keys import IdempotencyCacheKey
from src.utils.enums import IdempotencyStatus
from src.utils.exceptions import (
    IdempotencyPayloadMismatch,
    IdempotencyRequestInProgress,
    IdempotencyStateError,
)

logger = structlog.get_logger(__name__)


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
        idempotency_key: uuid.UUID = Header(
            alias="Idempotency-Key",
            description=(
                "Client-generated UUID. Attach before the first attempt and reuse on every retry."
                "The server returns the original response without re-executing the operation if the key is already complete."
            ),
        ),
    ) -> str:
        return str(idempotency_key)

    return idempotency_key_dependency


async def acquire_idempotency_lock(
    session: AsyncSession,
    redis: Redis,
    *,
    actor_id: int,
    operation: str,
    idempotency_key: str,
    payload_hash: str,
) -> None:
    """
    Acquire an idempotency lock for this operation.

    Uses the same SQLAlchemy session as the business operation so that
    the PROCESSING record and all business data participate in a single
    transaction. If the business operation fails and the transaction rolls
    back, the PROCESSING record is also rolled back — no cleanup needed,
    the client can retry freely with the same key.
    """

    cache_key = IdempotencyCacheKey.idempotency_key(
        operation, actor_id, idempotency_key
    )

    cached_data = await redis.get(cache_key)
    if cached_data is not None:
        _evaluate_cached(json.loads(cached_data), payload_hash)

        return

    result = await session.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.actor_id == actor_id,
            IdempotencyRecord.key == idempotency_key,
        )
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        if existing.status == IdempotencyStatus.PROCESSING:
            try:
                await redis.set(
                    cache_key,
                    json.dumps(
                        {
                            "status": "processing",
                            "request_hash": existing.request_hash,
                        }
                    ),
                    ex=get_settings().IDEMPOTENCY_PROCESSING_TTL,
                )
            except RedisError as exc:
                logger.warning(
                    "idempotency_processing_cache_mirror_failed",
                    operation=operation,
                    actor_id=actor_id,
                    error=str(exc),
                )

            raise IdempotencyRequestInProgress()

        if existing.request_hash != payload_hash:
            raise IdempotencyPayloadMismatch()

        await _mirror_complete_to_redis(
            redis,
            cache_key,
            payload_hash=existing.request_hash,
            http_status=existing.http_status,
            body=existing.response_body,
        )

        raise _CachedResponseSignal(
            status_code=existing.http_status,
            body=existing.response_body,
        )

    try:
        record = IdempotencyRecord(
            operation=operation,
            actor_id=actor_id,
            key=idempotency_key,
            request_hash=payload_hash,
            status=IdempotencyStatus.PROCESSING,
            expires_at=datetime.now(UTC)
            + timedelta(seconds=get_settings().IDEMPOTENCY_KEY_TTL),
        )

        session.add(record)
        await session.flush()

    except IntegrityError as exc:
        await session.rollback()

        raise IdempotencyRequestInProgress() from exc


async def complete_idempotency_record(
    session: AsyncSession,
    *,
    actor_id: int,
    operation: str,
    idempotency_key: str,
    payload_hash: str,
    http_status: int,
    body: dict,
) -> None:
    """
    Update the idempotency record from PROCESSING to COMPLETE.

    Uses the same session as the business operation — no commit here.
    The use case commits PROCESSING + business data + COMPLETE atomically.

    Redis is updated after the commit in the use case, not here, because
    writing to Redis before the commit would create a window where Redis
    says COMPLETE but PostgreSQL has not yet committed.
    """

    query = (
        update(IdempotencyRecord)
        .where(
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.actor_id == actor_id,
            IdempotencyRecord.key == idempotency_key,
            IdempotencyRecord.status == IdempotencyStatus.PROCESSING,
            IdempotencyRecord.request_hash == payload_hash,
        )
        .values(
            status=IdempotencyStatus.COMPLETE,
            http_status=http_status,
            response_body=body,
        )
    )

    result = await session.execute(query)

    if result.rowcount != 1:
        raise IdempotencyStateError()


async def mirror_complete_to_redis_after_commit(
    redis: Redis,
    *,
    actor_id: int,
    operation: str,
    idempotency_key: str,
    payload_hash: str,
    http_status: int,
    body: dict,
) -> None:
    """
    Write the completed idempotency response to Redis after the DB commit.

    Called by the use case after session.commit() succeeds. If this fails,
    the next request will fall through to the DB, find COMPLETE, and
    re-mirror to Redis — correctness is preserved, just one extra DB query.
    """

    cache_key = IdempotencyCacheKey.idempotency_key(
        operation, actor_id, idempotency_key
    )

    await _mirror_complete_to_redis(
        redis,
        cache_key,
        payload_hash,
        http_status,
        body=body,
    )


# Internal helpers
async def _mirror_complete_to_redis(
    redis: Redis,
    cache_key: str,
    payload_hash: str,
    http_status: int,
    body: dict,
) -> None:
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
        ex=get_settings().IDEMPOTENCY_KEY_TTL,
    )


def _evaluate_cached(data: dict, payload_hash: str) -> None:
    """
    Evaluate a Redis cache hit and raise the appropriate signal or exception.
    Always raises — never returns normally.
    """

    if data.get("status") == "processing":
        raise IdempotencyRequestInProgress()

    if data.get("request_hash") != payload_hash:
        raise IdempotencyPayloadMismatch()

    raise _CachedResponseSignal(
        status_code=data["http_status"],
        body=data["body"],
    )


class _CachedResponseSignal(Exception):
    """
    Signals the HTTP layer to return a previously cached idempotency response.

    Not an AppException — this is not an error. It is an internal signal
    that short-circuits the normal response path and replays a stored result.
    Registered as an exception handler in main.py.
    """

    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self.body = body


def make_cached_response(signal: _CachedResponseSignal) -> JSONResponse:
    """Convert a _CachedResponseSignal into a JSONResponse."""

    return JSONResponse(status_code=signal.status_code, content=signal.body)
