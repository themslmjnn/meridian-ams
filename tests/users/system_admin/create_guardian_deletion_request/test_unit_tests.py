import uuid
from datetime import UTC, datetime
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
    GuardianAlreadyPendingDeletionError,
    InvalidStatusTransitionError,
)
from src.users.utils.schemas import LoadOptionsSchema
from tests.factories import make_guardian, make_student

ENDPOINT = "/api/v1/admin/users"


class TestNotFound:
    async def test_raises_for_unknown_public_id(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ):
        with pytest.raises(CredentialsNotFoundError):
            await UserService.create_guardian_deletion_request(
                test_session,
                redis_client,
                system_admin.id,
                uuid.uuid4(),
            )

    async def test_raises_for_non_guardian_public_id(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ):
        student = await make_student(test_session)

        with pytest.raises(CredentialsNotFoundError):
            await UserService.create_guardian_deletion_request(
                test_session,
                redis_client,
                system_admin.id,
                student.public_id,
            )


class TestStatusValidation:
    async def test_raises_when_already_pending_deletion(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ):
        guardian = await make_guardian(test_session, status=UserStatus.PENDING_DELETION)

        with pytest.raises(GuardianAlreadyPendingDeletionError):
            await UserService.create_guardian_deletion_request(
                test_session,
                redis_client,
                system_admin.id,
                guardian.public_id,
            )

    @pytest.mark.parametrize(
        "invalid_status",
        [
            UserStatus.GRADUATED,
            UserStatus.EXPELLED,
            UserStatus.WITHDRAWN,
        ],
    )
    async def test_raises_for_invalid_status_transition(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        invalid_status: UserStatus,
    ):
        guardian = await make_guardian(test_session, status=invalid_status)

        with pytest.raises(InvalidStatusTransitionError):
            await UserService.create_guardian_deletion_request(
                test_session,
                redis_client,
                system_admin.id,
                guardian.public_id,
            )


class TestSuccess:
    async def test_status_set_to_pending_deletion(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        mock_send_account_deletion_email,
    ):
        guardian = await make_guardian(test_session)
        actor_id = system_admin.id

        await UserService.create_guardian_deletion_request(
            test_session, redis_client, actor_id, guardian.public_id
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session, guardian.public_id
        )

        assert updated.status == UserStatus.PENDING_DELETION

    async def test_pre_transition_status_preserved(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        mock_send_account_deletion_email,
    ):
        guardian = await make_guardian(test_session, status=UserStatus.ACTIVE)
        actor_id = system_admin.id

        await UserService.create_guardian_deletion_request(
            test_session, redis_client, actor_id, guardian.public_id
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session, guardian.public_id
        )

        assert updated.pre_transition_status == UserStatus.ACTIVE

    async def test_deletion_scheduled_for_set(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        mock_send_account_deletion_email,
    ):
        guardian = await make_guardian(test_session)
        actor_id = system_admin.id
        before = datetime.now(UTC)

        await UserService.create_guardian_deletion_request(
            test_session, redis_client, actor_id, guardian.public_id
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session, guardian.public_id
        )

        assert updated.deletion_scheduled_for is not None
        assert updated.deletion_scheduled_for > before

    async def test_sessions_invalidated(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        mock_send_account_deletion_email,
    ):
        guardian = await make_guardian(test_session)
        actor_id = system_admin.id

        await UserService.create_guardian_deletion_request(
            test_session, redis_client, actor_id, guardian.public_id
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session,
            guardian.public_id,
            load_options=LoadOptionsSchema(load_sessions=True),
        )

        for s in updated.sessions:
            assert s.refresh_token_hash is None
            assert s.refresh_token_family is None
            assert s.refresh_token_expires_at is None

    async def test_deletion_email_queued(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        mock_send_account_deletion_email,
    ):
        guardian = await make_guardian(test_session)
        actor_id = system_admin.id

        await UserService.create_guardian_deletion_request(
            test_session, redis_client, actor_id, guardian.public_id
        )

        mock_send_account_deletion_email.assert_called_once()

    async def test_cache_deleted_for_user_and_sessions(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        mock_send_account_deletion_email,
    ):
        guardian = await make_guardian(test_session)
        actor_id = system_admin.id

        with patch(
            "src.users.services.system_admin.delete_cache",
            new_callable=AsyncMock,
        ) as mock_delete_cache:
            await UserService.create_guardian_deletion_request(
                test_session, redis_client, actor_id, guardian.public_id
            )

            mock_delete_cache.assert_called_once()
            call_args = mock_delete_cache.call_args

            # redis client is first positional arg
            passed_keys = call_args.args[1:]
            key_strings = [str(k) for k in passed_keys]

            assert any(str(guardian.public_id) in k for k in key_strings), (
                "Expected user detail cache keys to include the guardian public_id"
            )

    @pytest.mark.parametrize(
        "initial_status",
        [
            UserStatus.ACTIVE,
            UserStatus.DEACTIVATED,
            UserStatus.PENDING_ACTIVATION,
        ],
    )
    async def test_all_valid_statuses_transition_to_pending_deletion(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
        initial_status: UserStatus,
        mock_send_account_deletion_email,
    ):
        guardian = await make_guardian(test_session, status=initial_status)
        actor_id = system_admin.id

        await UserService.create_guardian_deletion_request(
            test_session, redis_client, actor_id, guardian.public_id
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session, guardian.public_id
        )

        assert updated.status == UserStatus.PENDING_DELETION
        assert updated.pre_transition_status == initial_status
