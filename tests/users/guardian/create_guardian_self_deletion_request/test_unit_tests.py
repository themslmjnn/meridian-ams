from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.services.guardian import UserServiceGuardian
from src.users.utils.enums import UserStatus
from src.users.utils.exceptions import (
    GuardianAlreadyPendingDeletionError,
    InvalidStatusTransitionError,
)
from tests.factories import make_guardian

DELETION_ENDPOINT = "/api/v1/users/me/deletion"


@pytest.fixture
def mock_guardian_advisory_lock(mocker):
    return mocker.patch("src.users.services.guardian.acquire_contact_locks")


@pytest.fixture
def mock_guardian_check_contact_limit(mocker):
    return mocker.patch("src.users.services.guardian.check_contact_limit")


@pytest.fixture
def mock_guardian_delete_cache(mocker):
    return mocker.patch("src.users.services.guardian.delete_cache")


@pytest.fixture
def mock_guardian_send_deletion_email(mocker):
    return mocker.patch(
        "src.users.services.guardian.emails.send_account_deletion_email"
    )


@pytest.fixture
def mock_guardian_send_info_updated_email(mocker):
    return mocker.patch(
        "src.users.services.guardian.emails.send_account_info_updated_email"
    )


class TestStatusValidation:
    async def test_raises_when_already_pending_deletion(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        user = await make_guardian(test_session, status=UserStatus.PENDING_DELETION)

        with pytest.raises(GuardianAlreadyPendingDeletionError):
            await UserServiceGuardian.create_guardian_self_deletion_request(
                test_session, redis_client, user.id
            )

    async def test_raises_when_inactive(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        user = await make_guardian(test_session, status=UserStatus.DEACTIVATED)

        with pytest.raises(InvalidStatusTransitionError):
            await UserServiceGuardian.create_guardian_self_deletion_request(
                test_session, redis_client, user.id
            )

    async def test_raises_when_pending_activation(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        user = await make_guardian(test_session, status=UserStatus.PENDING_ACTIVATION)

        with pytest.raises(InvalidStatusTransitionError):
            await UserServiceGuardian.create_guardian_self_deletion_request(
                test_session, redis_client, user.id
            )


class TestSuccess:
    async def test_status_set_to_pending_deletion(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_delete_cache,
        mock_guardian_send_deletion_email,
    ):
        user = await make_guardian(test_session)

        await UserServiceGuardian.create_guardian_self_deletion_request(
            test_session, redis_client, user.id
        )

        await test_session.refresh(user)
        assert user.status == UserStatus.PENDING_DELETION

    async def test_deletion_scheduled_for_is_set(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_delete_cache,
        mock_guardian_send_deletion_email,
    ):
        from datetime import UTC, datetime

        user = await make_guardian(test_session)

        await UserServiceGuardian.create_guardian_self_deletion_request(
            test_session, redis_client, user.id
        )

        await test_session.refresh(user)
        assert user.deletion_scheduled_for is not None
        assert user.deletion_scheduled_for > datetime.now(UTC)

    async def test_pre_deletion_status_recorded(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_delete_cache,
        mock_guardian_send_deletion_email,
    ):
        user = await make_guardian(test_session, status=UserStatus.ACTIVE)

        await UserServiceGuardian.create_guardian_self_deletion_request(
            test_session, redis_client, user.id
        )

        await test_session.refresh(user)
        assert user.pre_transition_status == UserStatus.ACTIVE

    async def test_sessions_invalidated(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_delete_cache,
        mock_guardian_send_deletion_email,
    ):
        from src.users.repository.user import UserSessionRepository

        user = await make_guardian(test_session)
        session_row = await UserSessionRepository.get_by_credentials_id(
            test_session, user.id
        )
        original_atv = session_row.access_token_version

        await UserServiceGuardian.create_guardian_self_deletion_request(
            test_session, redis_client, user.id
        )

        await test_session.refresh(session_row)
        assert session_row.access_token_version == original_atv + 1
        assert session_row.refresh_token_hash is None
        assert session_row.refresh_token_family is None

    async def test_cache_deleted(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_delete_cache,
        mock_guardian_send_deletion_email,
    ):
        user = await make_guardian(test_session)

        await UserServiceGuardian.create_guardian_self_deletion_request(
            test_session, redis_client, user.id
        )

        mock_guardian_delete_cache.assert_called_once()

    async def test_deletion_email_fired(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_delete_cache,
        mocker,
    ):
        mock_send = mocker.patch(
            "src.users.services.guardian.emails.send_account_deletion_email",
            return_value=AsyncMock(),
        )
        mocker.patch(
            "src.users.services.guardian.emails.send_email_safe",
            new_callable=AsyncMock,
        )

        user = await make_guardian(test_session)

        await UserServiceGuardian.create_guardian_self_deletion_request(
            test_session, redis_client, user.id
        )

        mock_send.assert_called_once_with(user.email)
