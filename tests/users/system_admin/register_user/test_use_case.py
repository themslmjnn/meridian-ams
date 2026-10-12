import uuid
from unittest.mock import patch

import pytest
from redis import RedisError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.idempotency.repository import IdempotencyRepository
from src.core.idempotency.service import _CachedResponseSignal
from src.core.idempotency.utils.enums import IdempotencyOperation
from src.core.idempotency.utils.exceptions import IdempotencyPayloadMismatch
from src.users.models.credentials import UserCredentials
from src.users.schemas.system_admin import CreateStaff
from src.users.use_cases.register_user import RegisterUserUseCase
from src.users.utils.enums import AccountType, UserRole, UserStatus


class TestRegisterUserUseCase:
    async def test_successful_registration(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
        idempotency_key: uuid.UUID,
        mock_register_user_acquire_idempotency_lock,
        mock_register_user_complete_idempotency_record,
        mock_register_user_mirror_complete_to_redis_after_commit,
        mock_users_admin_acquire_contact_locks,
        mock_users_admin_check_contact_limit,
    ):
        mock_register_user_acquire_idempotency_lock.return_value = None
        mock_register_user_complete_idempotency_record.return_value = None
        mock_register_user_mirror_complete_to_redis_after_commit.return_value = None

        result = await RegisterUserUseCase.execute(
            test_session,
            redis_client,
            system_admin.id,
            valid_staff_payload,
            idempotency_key,
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
        idempotency_key: uuid.UUID,
        mock_register_user_acquire_idempotency_lock,
    ):
        original_body = {
            "public_id": str(uuid.uuid4()),
            "username": valid_staff_payload.username,
        }

        mock_register_user_acquire_idempotency_lock.side_effect = _CachedResponseSignal(
            status_code=201, body=original_body
        )

        with pytest.raises(_CachedResponseSignal) as exc_info:
            await RegisterUserUseCase.execute(
                test_session,
                redis_client,
                system_admin.id,
                valid_staff_payload,
                idempotency_key,
            )

        assert exc_info.value.status_code == 201
        assert exc_info.value.body == original_body

    async def test_payload_mismatch_raises(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
        idempotency_key: uuid.UUID,
        mock_register_user_acquire_idempotency_lock,
    ):
        mock_register_user_acquire_idempotency_lock.side_effect = (
            IdempotencyPayloadMismatch()
        )

        with pytest.raises(IdempotencyPayloadMismatch):
            await RegisterUserUseCase.execute(
                test_session,
                redis_client,
                system_admin.id,
                valid_staff_payload,
                idempotency_key,
            )

    async def test_business_error_rolls_back_idempotency_record(
        self,
        test_session: AsyncSession,
        redis_client,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
        idempotency_key: uuid.UUID,
        mock_users_admin_acquire_contact_locks,
        mock_users_admin_check_contact_limit,
    ):
        actor_id = system_admin.id

        with (
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
                idempotency_key,
            )

        await test_session.rollback()

        result = await IdempotencyRepository.get_record(
            test_session,
            operation=IdempotencyOperation.REGISTER_USER,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )

        assert result is None

    async def test_completion_failure_does_not_commit(
        self,
        test_session: AsyncSession,
        redis_client,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
        idempotency_key: uuid.UUID,
        mock_register_user_complete_idempotency_record,
        mock_users_admin_acquire_contact_locks,
        mock_users_admin_check_contact_limit,
    ):
        actor_id = system_admin.id

        mock_register_user_complete_idempotency_record.side_effect = RuntimeError(
            "complete failed"
        )

        with pytest.raises(RuntimeError, match="complete failed"):
            await RegisterUserUseCase.execute(
                test_session,
                redis_client,
                actor_id,
                valid_staff_payload,
                idempotency_key,
            )

        await test_session.rollback()

        result = await IdempotencyRepository.get_record(
            test_session,
            operation=IdempotencyOperation.REGISTER_USER,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )

        assert result is None

    async def test_redis_mirror_failure_does_not_raise(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
        idempotency_key: uuid.UUID,
        mock_register_user_acquire_idempotency_lock,
        mock_register_user_complete_idempotency_record,
        mock_register_user_mirror_complete_to_redis_after_commit,
        mock_users_admin_acquire_contact_locks,
        mock_users_admin_check_contact_limit,
    ):
        mock_register_user_mirror_complete_to_redis_after_commit.side_effect = (
            RedisError("redis down")
        )

        result = await RegisterUserUseCase.execute(
            test_session,
            redis_client,
            system_admin.id,
            valid_staff_payload,
            idempotency_key,
        )

        assert result.username == valid_staff_payload.username
