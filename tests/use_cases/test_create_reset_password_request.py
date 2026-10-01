import uuid
from unittest.mock import patch

import pytest
from redis import RedisError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.idempotency import _CachedResponseSignal
from src.core.models import IdempotencyRecord
from src.users.models.credentials import UserCredentials
from src.users.use_cases.create_reset_password_request import (
    CreateResetPasswordRequestUseCase,
)
from src.utils.enums import IdempotencyOperation
from src.utils.exceptions import IdempotencyPayloadMismatch


def _idempotency_key() -> str:
    return str(uuid.uuid4())


class TestCreateResetPasswordRequestUseCase:
    async def test_successful_execution(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ):
        actor_id = system_admin.id
        public_id = uuid.uuid4()
        key = _idempotency_key()

        with (
            patch(
                "src.users.use_cases.create_reset_password_request.UserService.create_reset_password_request"
            ),
            patch(
                "src.users.use_cases.create_reset_password_request.acquire_idempotency_lock"
            ),
            patch(
                "src.users.use_cases.create_reset_password_request.complete_idempotency_record"
            ),
            patch(
                "src.users.use_cases.create_reset_password_request.mirror_complete_to_redis_after_commit"
            ),
        ):
            result = await CreateResetPasswordRequestUseCase.execute(
                test_session,
                redis_client,
                actor_id,
                public_id,
                key,
            )

        assert result is None

    async def test_idempotent_retry_raises_cached_response_signal(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ):
        actor_id = system_admin.id
        public_id = uuid.uuid4()
        key = _idempotency_key()

        with (
            patch(
                "src.users.use_cases.create_reset_password_request.acquire_idempotency_lock",
                side_effect=_CachedResponseSignal(status_code=204, body=None),
            ),
            pytest.raises(_CachedResponseSignal) as exc_info,
        ):
            await CreateResetPasswordRequestUseCase.execute(
                test_session,
                redis_client,
                actor_id,
                public_id,
                key,
            )

        assert exc_info.value.status_code == 204
        assert exc_info.value.body is None

    async def test_payload_mismatch_raises(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ):
        actor_id = system_admin.id
        key = _idempotency_key()

        with (
            patch(
                "src.users.use_cases.create_reset_password_request.acquire_idempotency_lock",
                side_effect=IdempotencyPayloadMismatch(),
            ),
            pytest.raises(IdempotencyPayloadMismatch),
        ):
            await CreateResetPasswordRequestUseCase.execute(
                test_session,
                redis_client,
                actor_id,
                uuid.uuid4(),
                key,
            )

    async def test_business_error_rolls_back_idempotency_record(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ):
        actor_id = system_admin.id
        public_id = uuid.uuid4()
        key = _idempotency_key()

        with (
            patch(
                "src.users.use_cases.create_reset_password_request.UserService.create_reset_password_request",
                side_effect=RuntimeError("unexpected service failure"),
            ),
            pytest.raises(RuntimeError, match="unexpected service failure"),
        ):
            await CreateResetPasswordRequestUseCase.execute(
                test_session,
                redis_client,
                actor_id,
                public_id,
                key,
            )

        await test_session.rollback()

        result = await test_session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.operation
                == IdempotencyOperation.ADMIN_RESET_PASSWORD,
                IdempotencyRecord.actor_id == actor_id,
                IdempotencyRecord.key == key,
            )
        )
        assert result.scalar_one_or_none() is None

    async def test_completion_failure_does_not_commit(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ):
        actor_id = system_admin.id
        public_id = uuid.uuid4()
        key = _idempotency_key()

        with (
            patch(
                "src.users.use_cases.create_reset_password_request.UserService.create_reset_password_request"
            ),
            patch(
                "src.users.use_cases.create_reset_password_request.complete_idempotency_record",
                side_effect=RuntimeError("complete failed"),
            ),
            pytest.raises(RuntimeError, match="complete failed"),
        ):
            await CreateResetPasswordRequestUseCase.execute(
                test_session,
                redis_client,
                actor_id,
                public_id,
                key,
            )

        await test_session.rollback()

        result = await test_session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.operation
                == IdempotencyOperation.ADMIN_RESET_PASSWORD,
                IdempotencyRecord.actor_id == actor_id,
                IdempotencyRecord.key == key,
            )
        )
        assert result.scalar_one_or_none() is None

    async def test_redis_mirror_failure_does_not_raise(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ):
        actor_id = system_admin.id
        public_id = uuid.uuid4()
        key = _idempotency_key()

        with (
            patch(
                "src.users.use_cases.create_reset_password_request.UserService.create_reset_password_request"
            ),
            patch(
                "src.users.use_cases.create_reset_password_request.acquire_idempotency_lock"
            ),
            patch(
                "src.users.use_cases.create_reset_password_request.complete_idempotency_record"
            ),
            patch(
                "src.users.use_cases.create_reset_password_request.mirror_complete_to_redis_after_commit",
                side_effect=RedisError("redis down"),
            ),
        ):
            result = await CreateResetPasswordRequestUseCase.execute(
                test_session,
                redis_client,
                actor_id,
                public_id,
                key,
            )

        assert result is None
