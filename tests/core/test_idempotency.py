import json
import uuid

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.idempotency import (
    _CachedResponseSignal,
    acquire_idempotency_lock,
    complete_idempotency_record,
    hash_payload,
    mirror_complete_to_redis_after_commit,
)
from src.core.models import IdempotencyRecord
from src.utils.cache_keys import IdempotencyCacheKey
from src.utils.enums import IdempotencyStatus
from src.utils.exceptions import (
    IdempotencyPayloadMismatch,
    IdempotencyRequestInProgress,
    IdempotencyStateError,
)
from tests.factories import make_idempotency_record

OPERATION = "test_operation"
ACTOR_ID = 1
PAYLOAD = {"username": "testuser", "email": "test@example.com"}
PAYLOAD_HASH = hash_payload(PAYLOAD)


def _idempotency_key() -> str:
    return str(uuid.uuid4())


class TestHashPayload:
    def test_same_dict_produces_same_hash(self) -> None:
        assert hash_payload(PAYLOAD) == hash_payload(PAYLOAD)

    def test_different_dict_produces_different_hash(self) -> None:
        other = {"username": "other", "email": "other@example.com"}

        assert hash_payload(PAYLOAD) != hash_payload(other)

    def test_key_order_does_not_affect_hash(self) -> None:
        a = {"b": 2, "a": 1}
        b = {"a": 1, "b": 2}

        assert hash_payload(a) == hash_payload(b)

    def test_hash_is_64_chars(self) -> None:
        assert len(hash_payload(PAYLOAD)) == 64


class TestAcquireIdempotencyLockCacheHit:
    async def test_cache_processing_raises_in_progress(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ) -> None:
        key = _idempotency_key()
        cache_key = IdempotencyCacheKey.idempotency_key(OPERATION, ACTOR_ID, key)

        await redis_client.set(
            cache_key,
            json.dumps({"status": "processing", "request_hash": PAYLOAD_HASH}),
        )

        with pytest.raises(IdempotencyRequestInProgress):
            await acquire_idempotency_lock(
                test_session,
                redis_client,
                operation=OPERATION,
                actor_id=ACTOR_ID,
                idempotency_key=key,
                payload_hash=PAYLOAD_HASH,
            )

    async def test_cache_complete_matching_hash_raises_signal(
        self,
        test_session: AsyncSession,
        redis_client,
    ) -> None:
        key = _idempotency_key()
        cache_key = IdempotencyCacheKey.idempotency_key(OPERATION, ACTOR_ID, key)
        body = {"public_id": str(uuid.uuid4())}

        await redis_client.set(
            cache_key,
            json.dumps(
                {
                    "status": "complete",
                    "request_hash": PAYLOAD_HASH,
                    "http_status": 201,
                    "body": body,
                }
            ),
        )

        with pytest.raises(_CachedResponseSignal) as exc_info:
            await acquire_idempotency_lock(
                test_session,
                redis_client,
                operation=OPERATION,
                actor_id=ACTOR_ID,
                idempotency_key=key,
                payload_hash=PAYLOAD_HASH,
            )

        assert exc_info.value.status_code == 201
        assert exc_info.value.body == body

    async def test_cache_complete_mismatched_hash_raises_payload_mismatch(
        self,
        test_session: AsyncSession,
        redis_client,
    ) -> None:
        key = _idempotency_key()
        cache_key = IdempotencyCacheKey.idempotency_key(OPERATION, ACTOR_ID, key)

        await redis_client.set(
            cache_key,
            json.dumps(
                {
                    "status": "complete",
                    "request_hash": "different_hash_entirely",
                    "http_status": 201,
                    "body": {},
                }
            ),
        )

        with pytest.raises(IdempotencyPayloadMismatch):
            await acquire_idempotency_lock(
                test_session,
                redis_client,
                operation=OPERATION,
                actor_id=ACTOR_ID,
                idempotency_key=key,
                payload_hash=PAYLOAD_HASH,
            )


class TestAcquireIdempotencyLockDbFallback:
    async def test_db_processing_raises_in_progress(
        self,
        test_session: AsyncSession,
        redis_client,
    ) -> None:
        key = _idempotency_key()
        await make_idempotency_record(
            test_session,
            actor_id=ACTOR_ID,
            operation=OPERATION,
            key=key,
            status=IdempotencyStatus.PROCESSING,
            request_hash=PAYLOAD_HASH,
        )

        with pytest.raises(IdempotencyRequestInProgress):
            await acquire_idempotency_lock(
                test_session,
                redis_client,
                operation=OPERATION,
                actor_id=ACTOR_ID,
                idempotency_key=key,
                payload_hash=PAYLOAD_HASH,
            )

    async def test_db_processing_mirrors_to_redis(
        self,
        test_session: AsyncSession,
        redis_client,
    ) -> None:
        key = _idempotency_key()
        cache_key = IdempotencyCacheKey.idempotency_key(OPERATION, ACTOR_ID, key)
        await make_idempotency_record(
            test_session,
            actor_id=ACTOR_ID,
            operation=OPERATION,
            key=key,
            status=IdempotencyStatus.PROCESSING,
            request_hash=PAYLOAD_HASH,
        )

        with pytest.raises(IdempotencyRequestInProgress):
            await acquire_idempotency_lock(
                test_session,
                redis_client,
                operation=OPERATION,
                actor_id=ACTOR_ID,
                idempotency_key=key,
                payload_hash=PAYLOAD_HASH,
            )

        cached = await redis_client.get(cache_key)
        assert cached is not None
        data = json.loads(cached)
        assert data["status"] == "processing"

    async def test_db_complete_matching_hash_raises_signal(
        self,
        test_session: AsyncSession,
        redis_client,
    ) -> None:
        key = _idempotency_key()
        body = {"public_id": str(uuid.uuid4())}

        await make_idempotency_record(
            test_session,
            actor_id=ACTOR_ID,
            operation=OPERATION,
            key=key,
            status=IdempotencyStatus.COMPLETE,
            request_hash=PAYLOAD_HASH,
            http_status=201,
            response_body=body,
        )

        with pytest.raises(_CachedResponseSignal) as exc_info:
            await acquire_idempotency_lock(
                test_session,
                redis_client,
                operation=OPERATION,
                actor_id=ACTOR_ID,
                idempotency_key=key,
                payload_hash=PAYLOAD_HASH,
            )

        assert exc_info.value.status_code == 201
        assert exc_info.value.body == body

    async def test_db_complete_matching_hash_mirrors_to_redis(
        self,
        test_session: AsyncSession,
        redis_client,
    ) -> None:
        key = _idempotency_key()
        cache_key = IdempotencyCacheKey.idempotency_key(OPERATION, ACTOR_ID, key)
        body = {"public_id": str(uuid.uuid4())}
        await make_idempotency_record(
            test_session,
            actor_id=ACTOR_ID,
            operation=OPERATION,
            key=key,
            status=IdempotencyStatus.COMPLETE,
            request_hash=PAYLOAD_HASH,
            http_status=201,
            response_body=body,
        )

        with pytest.raises(_CachedResponseSignal):
            await acquire_idempotency_lock(
                test_session,
                redis_client,
                operation=OPERATION,
                actor_id=ACTOR_ID,
                idempotency_key=key,
                payload_hash=PAYLOAD_HASH,
            )

        cached = await redis_client.get(cache_key)
        assert cached is not None
        data = json.loads(cached)
        assert data["status"] == "complete"
        assert data["body"] == body
        assert data["http_status"] == 201

    async def test_db_complete_mismatched_hash_raises_payload_mismatch(
        self,
        test_session: AsyncSession,
        redis_client,
    ) -> None:
        key = _idempotency_key()
        await make_idempotency_record(
            test_session,
            actor_id=ACTOR_ID,
            operation=OPERATION,
            key=key,
            status=IdempotencyStatus.COMPLETE,
            request_hash="different_hash_entirely",
            http_status=201,
            response_body={},
        )

        with pytest.raises(IdempotencyPayloadMismatch):
            await acquire_idempotency_lock(
                test_session,
                redis_client,
                operation=OPERATION,
                actor_id=ACTOR_ID,
                idempotency_key=key,
                payload_hash=PAYLOAD_HASH,
            )

    async def test_no_existing_record_inserts_processing_row(
        self,
        test_session: AsyncSession,
        redis_client,
    ) -> None:
        key = _idempotency_key()

        await acquire_idempotency_lock(
            test_session,
            redis_client,
            operation=OPERATION,
            actor_id=ACTOR_ID,
            idempotency_key=key,
            payload_hash=PAYLOAD_HASH,
        )

        query = select(IdempotencyRecord).where(
            IdempotencyRecord.operation == OPERATION,
            IdempotencyRecord.actor_id == ACTOR_ID,
            IdempotencyRecord.key == key,
        )
        result = await test_session.execute(query)
        record = result.scalar_one_or_none()

        assert record is not None
        assert record.status == IdempotencyStatus.PROCESSING
        assert record.request_hash == PAYLOAD_HASH

    async def test_no_existing_record_returns_normally(
        self,
        test_session: AsyncSession,
        redis_client,
    ) -> None:
        key = _idempotency_key()

        result = await acquire_idempotency_lock(
            test_session,
            redis_client,
            operation=OPERATION,
            actor_id=ACTOR_ID,
            idempotency_key=key,
            payload_hash=PAYLOAD_HASH,
        )

        assert result is None

    async def test_concurrent_insert_raises_in_progress(
        self,
        test_session: AsyncSession,
        redis_client,
    ) -> None:
        key = _idempotency_key()

        await acquire_idempotency_lock(
            test_session,
            redis_client,
            operation=OPERATION,
            actor_id=ACTOR_ID,
            idempotency_key=key,
            payload_hash=PAYLOAD_HASH,
        )

        with pytest.raises(IdempotencyRequestInProgress):
            await acquire_idempotency_lock(
                test_session,
                redis_client,
                operation=OPERATION,
                actor_id=ACTOR_ID,
                idempotency_key=key,
                payload_hash=PAYLOAD_HASH,
            )


class TestCompleteIdempotencyRecord:
    async def test_updates_processing_to_complete(
        self,
        test_session: AsyncSession,
    ) -> None:
        key = _idempotency_key()
        body = {"public_id": str(uuid.uuid4())}

        await make_idempotency_record(
            test_session,
            actor_id=ACTOR_ID,
            operation=OPERATION,
            key=key,
            status=IdempotencyStatus.PROCESSING,
            request_hash=PAYLOAD_HASH,
        )

        await complete_idempotency_record(
            test_session,
            operation=OPERATION,
            actor_id=ACTOR_ID,
            idempotency_key=key,
            payload_hash=PAYLOAD_HASH,
            http_status=201,
            body=body,
        )

        query = select(IdempotencyRecord).where(
            IdempotencyRecord.operation == OPERATION,
            IdempotencyRecord.actor_id == ACTOR_ID,
            IdempotencyRecord.key == key,
        )
        result = await test_session.execute(query)
        record = result.scalar_one()

        assert record.status == IdempotencyStatus.COMPLETE
        assert record.http_status == 201
        assert record.response_body == body

    async def test_raises_when_no_matching_record(
        self,
        test_session: AsyncSession,
    ) -> None:
        with pytest.raises(IdempotencyStateError):
            await complete_idempotency_record(
                test_session,
                operation=OPERATION,
                actor_id=ACTOR_ID,
                idempotency_key=_idempotency_key(),
                payload_hash=PAYLOAD_HASH,
                http_status=201,
                body={},
            )

    async def test_raises_when_record_already_complete(
        self,
        test_session: AsyncSession,
    ) -> None:
        key = _idempotency_key()
        body = {"public_id": str(uuid.uuid4())}
        await make_idempotency_record(
            test_session,
            actor_id=ACTOR_ID,
            operation=OPERATION,
            key=key,
            status=IdempotencyStatus.COMPLETE,
            request_hash=PAYLOAD_HASH,
            http_status=201,
            response_body=body,
        )

        with pytest.raises(IdempotencyStateError):
            await complete_idempotency_record(
                test_session,
                operation=OPERATION,
                actor_id=ACTOR_ID,
                idempotency_key=key,
                payload_hash=PAYLOAD_HASH,
                http_status=201,
                body=body,
            )


class TestMirrorCompleteToRedis:
    async def test_writes_correct_shape_to_redis(
        self,
        test_session: AsyncSession,
        redis_client,
    ) -> None:
        key = _idempotency_key()
        cache_key = IdempotencyCacheKey.idempotency_key(OPERATION, ACTOR_ID, key)
        body = {"public_id": str(uuid.uuid4())}

        await mirror_complete_to_redis_after_commit(
            redis_client,
            operation=OPERATION,
            actor_id=ACTOR_ID,
            idempotency_key=key,
            payload_hash=PAYLOAD_HASH,
            http_status=201,
            body=body,
        )

        cached = await redis_client.get(cache_key)
        assert cached is not None
        data = json.loads(cached)
        assert data["status"] == "complete"
        assert data["request_hash"] == PAYLOAD_HASH
        assert data["http_status"] == 201
        assert data["body"] == body

    async def test_written_under_correct_cache_key(
        self,
        test_session: AsyncSession,
        redis_client,
    ) -> None:
        key = _idempotency_key()
        other_key = _idempotency_key()
        cache_key = IdempotencyCacheKey.idempotency_key(OPERATION, ACTOR_ID, key)

        await mirror_complete_to_redis_after_commit(
            redis_client,
            operation=OPERATION,
            actor_id=ACTOR_ID,
            idempotency_key=key,
            payload_hash=PAYLOAD_HASH,
            http_status=201,
            body={},
        )

        correct_key_hit = await redis_client.get(cache_key)
        other_key_miss = await redis_client.get(
            IdempotencyCacheKey.idempotency_key(OPERATION, ACTOR_ID, other_key)
        )

        assert correct_key_hit is not None
        assert other_key_miss is None
