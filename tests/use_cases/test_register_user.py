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
from src.users.schemas.system_admin import CreateStaff
from src.users.use_cases.register_user import RegisterUserUseCase
from src.users.utils.enums import AccountType, UserRole, UserStatus
from src.utils.enums import IdempotencyOperation
from src.utils.exceptions import IdempotencyPayloadMismatch


def _idempotency_key() -> str:
    return str(uuid.uuid4())


class TestRegisterUserUseCase:
    async def test_successful_registration(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
    ) -> None:
        key = _idempotency_key()

        with (
            patch(
                "src.users.use_cases.register_user.acquire_idempotency_lock"
            ) as mock_acquire,
            patch(
                "src.users.use_cases.register_user.complete_idempotency_record"
            ) as mock_complete,
            patch(
                "src.users.use_cases.register_user.mirror_complete_to_redis_after_commit"
            ) as mock_mirror,
            patch("src.users.services.system_admin.acquire_contact_locks"),
            patch("src.users.services.system_admin.check_contact_limit"),
        ):
            mock_acquire.return_value = None
            mock_complete.return_value = None
            mock_mirror.return_value = None

            result = await RegisterUserUseCase.execute(
                test_session,
                redis_client,
                system_admin.id,
                valid_staff_payload,
                key,
            )

        assert result.username == valid_staff_payload.username
        assert result.email == valid_staff_payload.email
        assert result.role == UserRole.TEACHER
        assert result.account_type == AccountType.WORK
        assert result.status == UserStatus.PENDING_ACTIVATION

    async def test_idempotent_retry_returns_original_response(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
    ) -> None:
        key = _idempotency_key()
        original_body = {
            "public_id": str(uuid.uuid4()),
            "username": valid_staff_payload.username,
        }

        with (
            patch(
                "src.users.use_cases.register_user.acquire_idempotency_lock",
                side_effect=_CachedResponseSignal(status_code=201, body=original_body),
            ),
            pytest.raises(_CachedResponseSignal) as exc_info,
        ):
            await RegisterUserUseCase.execute(
                test_session,
                redis_client,
                system_admin.id,
                valid_staff_payload,
                key,
            )

        assert exc_info.value.status_code == 201
        assert exc_info.value.body == original_body

    async def test_payload_mismatch_raises(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
    ) -> None:
        key = _idempotency_key()

        with (
            patch(
                "src.users.use_cases.register_user.acquire_idempotency_lock",
                side_effect=IdempotencyPayloadMismatch(),
            ),
            pytest.raises(IdempotencyPayloadMismatch),
        ):
            await RegisterUserUseCase.execute(
                test_session,
                redis_client,
                system_admin.id,
                valid_staff_payload,
                key,
            )

    async def test_business_error_rolls_back_idempotency_record(
        self,
        test_session: AsyncSession,
        redis_client,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
    ) -> None:
        key = _idempotency_key()
        actor_id = system_admin.id  # capture before any rollback expires the object

        with (
            patch("src.users.services.system_admin.acquire_contact_locks"),
            patch("src.users.services.system_admin.check_contact_limit"),
            patch(
                "src.users.use_cases.register_user.UserService.register_user",
                side_effect=RuntimeError("unexpected domain failure"),
            ),
            pytest.raises(RuntimeError, match="unexpected domain failure"),
        ):
            await RegisterUserUseCase.execute(
                test_session,
                redis_client,
                actor_id,
                valid_staff_payload,
                key,
            )

        await test_session.rollback()

        result = await test_session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.operation == IdempotencyOperation.USER_REGISTER,
                IdempotencyRecord.actor_id == actor_id,
                IdempotencyRecord.key == key,
            )
        )
        assert result.scalar_one_or_none() is None

    async def test_completion_failure_does_not_commit(
        self,
        test_session: AsyncSession,
        redis_client,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
    ) -> None:
        key = _idempotency_key()
        actor_id = system_admin.id  # capture before any rollback expires the object

        with (
            patch("src.users.services.system_admin.acquire_contact_locks"),
            patch("src.users.services.system_admin.check_contact_limit"),
            patch(
                "src.users.use_cases.register_user.complete_idempotency_record",
                side_effect=RuntimeError("complete failed"),
            ),
            pytest.raises(RuntimeError, match="complete failed"),
        ):
            await RegisterUserUseCase.execute(
                test_session,
                redis_client,
                actor_id,
                valid_staff_payload,
                key,
            )

        await test_session.rollback()

        result = await test_session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.operation == IdempotencyOperation.USER_REGISTER,
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
        valid_staff_payload: CreateStaff,
    ) -> None:
        key = _idempotency_key()

        with (
            patch("src.users.use_cases.register_user.acquire_idempotency_lock"),
            patch("src.users.use_cases.register_user.complete_idempotency_record"),
            patch("src.users.services.system_admin.acquire_contact_locks"),
            patch("src.users.services.system_admin.check_contact_limit"),
            patch(
                "src.users.use_cases.register_user.mirror_complete_to_redis_after_commit",
                side_effect=RedisError("redis down"),
            ),
        ):
            result = await RegisterUserUseCase.execute(
                test_session,
                redis_client,
                system_admin.id,
                valid_staff_payload,
                key,
            )

        assert result.username == valid_staff_payload.username
