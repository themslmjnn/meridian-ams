import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Header
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from src.core.config import get_settings
from src.core.dependencies import redis_dependency
from src.core.models import IdempotencyRecord
from src.database.connection import session_factory
from src.utils.cache_keys import IdempotencyCacheKey
from src.utils.enums import IdempotencyStatus
from src.utils.exceptions import (
    IdempotencyPayloadMismatch,
    IdempotencyRequestInProgress,
)


def _hash_payload(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    return hashlib.sha256(canonical.encode()).hexdigest()


def make_idempotency_dependency():
    async def idempotency_dependency(
        idempotency_key: uuid.UUID = Header(
            alias="Idempotency-Key",
            description="Client-generated UUID. Safe to retry on network failure.",
        ),
    ) -> str:
        # Dependency doesn't have access to current_user or payload directly —
        # those are resolved in the route. The scoping and fingerprinting happen
        # in acquire_idempotency_lock() called from the router after resolution.
        return str(idempotency_key)

    return idempotency_dependency


async def acquire_idempotency_lock(
    redis: Redis,
    *,
    operation: str,
    actor_id: int,
    idempotency_key: str,
    payload_hash: str,
) -> None:
    """
    Uses its own session — completely independent from the business transaction.
    This means a failed business operation never corrupts idempotency state.
    """

    cache_key = IdempotencyCacheKey.idempotency_key(
        operation, actor_id, idempotency_key
    )

    cached_data = await redis.get(cache_key)
    if cached_data is not None:
        _evaluate_cached(json.loads(cached_data), payload_hash)

        return

    async with session_factory() as idempotency_session:
        result = await idempotency_session.execute(
            select(IdempotencyRecord).where(IdempotencyRecord.key == cache_key)
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            if existing.status == IdempotencyStatus.PROCESSING:
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

                raise IdempotencyRequestInProgress()

            if existing.request_hash != payload_hash:
                raise IdempotencyPayloadMismatch()

            body = existing.response_body
            http_status = existing.http_status

            await redis.set(
                cache_key,
                json.dumps(
                    {
                        "status": "complete",
                        "request_hash": existing.request_hash,
                        "http_status": http_status,
                        "body": body,
                    }
                ),
                ex=get_settings().IDEMPOTENCY_KEY_TTL,
            )

            raise _CachedResponseSignal(status_code=http_status, body=body)

        try:
            record = IdempotencyRecord(
                key=cache_key,
                operation=operation,
                actor_id=actor_id,
                request_hash=payload_hash,
                status=IdempotencyStatus.PROCESSING,
                expires_at=datetime.now(UTC)
                + timedelta(seconds=get_settings().IDEMPOTENCY_KEY_TTL),
            )

            idempotency_session.add(record)
            await idempotency_session.commit()

            await redis.set(
                cache_key,
                json.dumps({"status": "processing", "request_hash": payload_hash}),
                ex=get_settings().IDEMPOTENCY_PROCESSING_TTL,
            )

        except IntegrityError as exc:
            await idempotency_session.rollback()

            raise IdempotencyRequestInProgress() from exc


async def complete_idempotency_record(
    redis: Redis,
    *,
    operation: str,
    actor_id: int,
    idempotency_key: str,
    payload_hash: str,
    http_status: int,
    body: dict,
) -> None:
    """
    Also uses its own session — independent from the business transaction.
    Called after the business session has committed successfully.
    """
    cache_key = IdempotencyCacheKey.idempotency_key(
        operation, actor_id, idempotency_key
    )

    async with session_factory() as idempotency_session:
        await idempotency_session.execute(
            update(IdempotencyRecord)
            .where(IdempotencyRecord.key == cache_key)
            .values(
                status=IdempotencyStatus.COMPLETE,
                http_status=http_status,
                response_body=body,
            )
        )

        await idempotency_session.commit()

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
    if data.get("status") == "processing":
        raise IdempotencyRequestInProgress()

    if data.get("request_hash") != payload_hash:
        raise IdempotencyPayloadMismatch()

    raise _CachedResponseSignal(
        status_code=data["http_status"],
        body=data["body"],
    )


class _CachedResponseSignal(Exception):
    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self.body = body


def make_cached_response(signal: _CachedResponseSignal) -> JSONResponse:
    return JSONResponse(status_code=signal.status_code, content=signal.body)
