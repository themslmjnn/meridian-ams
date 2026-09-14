import uuid
from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserCredentialsRepository
from src.users.services.system_admin import UserService
from src.users.utils.enums import UserStatus
from src.users.utils.exceptions import (
    CredentialsNotFoundError,
    InvalidStatusTransitionError,
    UserAlreadyActiveError,
)
from src.users.utils.schemas import LoadOptionsSchema
from tests.factories import make_teacher

ENDPOINT = "/api/v1/admin/users"


class TestNotFound:
    async def test_unknown_public_id_raises(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ) -> None:
        with pytest.raises(CredentialsNotFoundError):
            await UserService.activate_user(
                test_session, redis_client, system_admin.id, uuid.uuid4()
            )

    async def test_system_admin_public_id_raises(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ) -> None:
        with pytest.raises(CredentialsNotFoundError):
            await UserService.activate_user(
                test_session,
                redis_client,
                system_admin.id,
                system_admin.public_id,
            )


class TestStatusValidation:
    async def test_already_active_raises(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ) -> None:
        with pytest.raises(UserAlreadyActiveError):
            await UserService.activate_user(
                test_session,
                redis_client,
                system_admin.id,
                teacher.public_id,
            )

    async def test_pending_activation_raises(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ) -> None:
        pending = await make_teacher(test_session, status=UserStatus.PENDING_ACTIVATION)

        with pytest.raises(InvalidStatusTransitionError):
            await UserService.activate_user(
                test_session,
                redis_client,
                system_admin.id,
                pending.public_id,
            )


class TestSuccessfulActivation:
    async def test_status_set_to_active(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        mock_users_delete_cache_system_admin,
    ) -> None:
        deactivated = await make_teacher(test_session, status=UserStatus.DEACTIVATED)

        await UserService.activate_user(
            test_session, redis_client, system_admin.id, deactivated.public_id
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session, deactivated.public_id
        )

        assert updated.status == UserStatus.ACTIVE

    async def test_login_lockout_reset(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        mock_users_delete_cache_system_admin,
    ) -> None:
        deactivated = await make_teacher(
            test_session,
            status=UserStatus.DEACTIVATED,
            failed_attempts=5,
            locked_until=datetime.now(UTC) + timedelta(minutes=30),
        )

        await UserService.activate_user(
            test_session, redis_client, system_admin.id, deactivated.public_id
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session,
            deactivated.public_id,
            load_options=LoadOptionsSchema(load_login_lockout=True),
        )

        assert updated.login_lockout.failed_attempts == 0
        assert updated.login_lockout.locked_until is None

    async def test_cache_deleted(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        mock_users_delete_cache_system_admin,
    ) -> None:
        deactivated = await make_teacher(test_session, status=UserStatus.DEACTIVATED)

        await UserService.activate_user(
            test_session, redis_client, system_admin.id, deactivated.public_id
        )

        mock_users_delete_cache_system_admin.assert_called_once()

    async def test_activation_email_fired(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        mock_users_delete_cache_system_admin,
        mock_send_account_activation_email,
    ) -> None:
        deactivated = await make_teacher(test_session, status=UserStatus.DEACTIVATED)

        await UserService.activate_user(
            test_session, redis_client, system_admin.id, deactivated.public_id
        )

        mock_send_account_activation_email.assert_called_once_with(deactivated.email)
