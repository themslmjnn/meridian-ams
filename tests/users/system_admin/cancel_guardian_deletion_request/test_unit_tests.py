import uuid
from unittest.mock import AsyncMock, patch

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserCredentialsRepository
from src.users.services.system_admin import UserService
from src.users.utils.enums import UserStatus
from src.users.utils.exceptions import (
    CredentialsNotFoundError,
    GuardianNotPendingDeletionError,
)
from tests.factories import make_guardian

ENDPOINT = "/api/v1/admin/users"


class TestNotFound:
    async def test_raises_for_unknown_public_id(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ):
        with pytest.raises(CredentialsNotFoundError):
            await UserService.cancel_guardian_deletion_request(
                test_session,
                redis_client,
                system_admin.id,
                uuid.uuid4(),
            )


class TestStatusValidation:
    @pytest.mark.parametrize(
        "invalid_status",
        [
            UserStatus.ACTIVE,
            UserStatus.DEACTIVATED,
            UserStatus.PENDING_ACTIVATION,
            UserStatus.GRADUATED,
            UserStatus.EXPELLED,
            UserStatus.WITHDRAWN,
        ],
    )
    async def test_raises_when_not_pending_deletion(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        invalid_status: UserStatus,
    ):
        guardian = await make_guardian(test_session, status=invalid_status)

        with pytest.raises(GuardianNotPendingDeletionError):
            await UserService.cancel_guardian_deletion_request(
                test_session,
                redis_client,
                system_admin.id,
                guardian.public_id,
            )


class TestRaceCondition:
    async def test_raises_when_reactivation_finds_no_row(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ):
        guardian = await make_guardian(test_session, status=UserStatus.PENDING_DELETION)
        actor_id = system_admin.id

        with (
            patch(
                "src.users.services.system_admin.UserCredentialsRepository.reactivate_pending_deletion_user",
                return_value=False,
            ),
            pytest.raises(CredentialsNotFoundError),
        ):
            await UserService.cancel_guardian_deletion_request(
                test_session,
                redis_client,
                actor_id,
                guardian.public_id,
            )


class TestSuccess:
    async def test_status_reverted_to_pre_transition_status(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        mock_send_account_deletion_canceled_email,
    ):
        guardian = await make_guardian(test_session, status=UserStatus.PENDING_DELETION)
        actor_id = system_admin.id

        # Simulate pre_transition_status being set (as done by create_guardian_deletion_request)
        guardian.pre_transition_status = UserStatus.ACTIVE
        await test_session.flush()

        await UserService.cancel_guardian_deletion_request(
            test_session, redis_client, actor_id, guardian.public_id
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session, guardian.public_id
        )

        assert updated.status == UserStatus.ACTIVE

    async def test_deletion_scheduled_for_cleared(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        mock_send_account_deletion_canceled_email,
    ):
        guardian = await make_guardian(test_session, status=UserStatus.PENDING_DELETION)
        actor_id = system_admin.id

        guardian.pre_transition_status = UserStatus.ACTIVE
        await test_session.flush()

        await UserService.cancel_guardian_deletion_request(
            test_session, redis_client, actor_id, guardian.public_id
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session, guardian.public_id
        )

        assert updated.deletion_scheduled_for is None

    async def test_cancellation_email_queued(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        mock_send_account_deletion_canceled_email,
    ):
        guardian = await make_guardian(test_session, status=UserStatus.PENDING_DELETION)
        actor_id = system_admin.id

        guardian.pre_transition_status = UserStatus.ACTIVE
        await test_session.flush()

        await UserService.cancel_guardian_deletion_request(
            test_session, redis_client, actor_id, guardian.public_id
        )

        mock_send_account_deletion_canceled_email.assert_called_once()

    async def test_cache_deleted_for_user(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ):
        guardian = await make_guardian(test_session, status=UserStatus.PENDING_DELETION)
        actor_id = system_admin.id

        guardian.pre_transition_status = UserStatus.ACTIVE
        await test_session.flush()

        with patch(
            "src.users.services.system_admin.delete_cache",
            new_callable=AsyncMock,
        ) as mock_delete_cache:
            await UserService.cancel_guardian_deletion_request(
                test_session, redis_client, actor_id, guardian.public_id
            )

            mock_delete_cache.assert_called_once()
            passed_keys = mock_delete_cache.call_args.args[1:]
            key_strings = [str(k) for k in passed_keys]

            assert any(str(guardian.public_id) in k for k in key_strings)

    @pytest.mark.parametrize(
        "pre_transition_status",
        [
            UserStatus.ACTIVE,
            UserStatus.DEACTIVATED,
            UserStatus.PENDING_ACTIVATION,
        ],
    )
    async def test_all_valid_pre_transition_statuses_restored(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        pre_transition_status: UserStatus,
    ):
        guardian = await make_guardian(test_session, status=UserStatus.PENDING_DELETION)
        actor_id = system_admin.id

        guardian.pre_transition_status = pre_transition_status
        await test_session.flush()

        await UserService.cancel_guardian_deletion_request(
            test_session, redis_client, actor_id, guardian.public_id
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session, guardian.public_id
        )

        assert updated.status == pre_transition_status
