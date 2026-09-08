import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserCredentialsRepository, UserSessionRepository
from src.users.services.system_admin import UserService
from src.users.utils.enums import UserStatus
from src.users.utils.exceptions import (
    CredentialsNotFoundError,
    InvalidStatusTransitionError,
    UserAlreadyInactiveError,
)
from tests.factories import make_teacher

ENDPOINT = "/api/v1/admin/users"


class TestNotFound:
    async def test_unknown_public_id_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        redis_client,
    ) -> None:
        with pytest.raises(CredentialsNotFoundError):
            await UserService.deactivate_user(
                test_session, redis_client, system_admin.id, uuid.uuid4()
            )

    async def test_system_admin_public_id_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        redis_client,
    ) -> None:
        with pytest.raises(CredentialsNotFoundError):
            await UserService.deactivate_user(
                test_session,
                redis_client,
                system_admin.id,
                system_admin.public_id,
            )


class TestStatusValidation:
    async def test_already_deactivated_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        redis_client,
    ) -> None:
        deactivated = await make_teacher(test_session, status=UserStatus.DEACTIVATED)

        with pytest.raises(UserAlreadyInactiveError):
            await UserService.deactivate_user(
                test_session,
                redis_client,
                system_admin.id,
                deactivated.public_id,
            )

    async def test_pending_activation_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        redis_client,
    ) -> None:
        pending = await make_teacher(test_session, status=UserStatus.PENDING_ACTIVATION)

        with pytest.raises(InvalidStatusTransitionError):
            await UserService.deactivate_user(
                test_session,
                redis_client,
                system_admin.id,
                pending.public_id,
            )

    async def test_pending_deletion_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        redis_client,
    ) -> None:
        pending_deletion = await make_teacher(
            test_session, status=UserStatus.PENDING_DELETION
        )

        with pytest.raises(InvalidStatusTransitionError):
            await UserService.deactivate_user(
                test_session,
                redis_client,
                system_admin.id,
                pending_deletion.public_id,
            )


class TestSuccess:
    async def test_status_set_to_deactivated(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_delete_cache_system_admin,
        redis_client,
    ) -> None:
        pre_deletion_status = teacher.status

        await UserService.deactivate_user(
            test_session, redis_client, system_admin.id, teacher.public_id
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session, teacher.public_id
        )

        assert updated.status == UserStatus.DEACTIVATED
        assert updated.pre_deletion_status == pre_deletion_status

    async def test_all_sessions_invalidated(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_delete_cache_system_admin,
        redis_client,
    ) -> None:
        user_session = await UserSessionRepository.get_by_credentials_id(
            test_session, teacher.id
        )
        old_atv = user_session.access_token_version

        await UserService.deactivate_user(
            test_session, redis_client, system_admin.id, teacher.public_id
        )

        user_session_after = await UserSessionRepository.get_by_credentials_id(
            test_session, teacher.id
        )

        assert user_session_after.access_token_version == old_atv + 1
        assert user_session_after.refresh_token_hash is None
        assert user_session_after.refresh_token_family is None

    async def test_cache_deleted(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_delete_cache_system_admin,
        redis_client,
    ) -> None:
        await UserService.deactivate_user(
            test_session, redis_client, system_admin.id, teacher.public_id
        )

        mock_users_delete_cache_system_admin.assert_called_once()

    async def test_deactivation_email_fired(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_delete_cache_system_admin,
        redis_client,
        mock_send_account_deactivation_email,
    ) -> None:
        await UserService.deactivate_user(
            test_session, redis_client, system_admin.id, teacher.public_id
        )

        mock_send_account_deactivation_email.assert_called_once()

    async def test_student_deactivated_successfully(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        student: UserCredentials,
        mock_users_delete_cache_system_admin,
        redis_client,
    ) -> None:
        await UserService.deactivate_user(
            test_session, redis_client, system_admin.id, student.public_id
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session, student.public_id
        )

        assert updated.status == UserStatus.DEACTIVATED
