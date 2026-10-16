from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.models.email_change import UserEmailChange
from src.users.repository.credentials import UserCredentialsRepository
from src.users.repository.session import UserSessionRepository
from src.users.schemas.shared import UpdateUserCredentials
from src.users.services.shared import UserServiceSelf
from src.users.utils.exceptions import (
    DuplicateEmailChangeRequestError,
    UsernameAlreadyTakenError,
)
from src.users.utils.schemas import LoadOptionsSchema
from src.utils.exceptions import NoChangesDetectedError
from tests.factories import make_teacher

ENDPOINT = "/api/v1/users/me/credentials"


@pytest.fixture
def mock_shared_delete_cache(mocker):
    return mocker.patch("src.users.services.shared.delete_cache")


@pytest.fixture
def mock_shared_send_email_change_verification(mocker):
    return mocker.patch(
        "src.users.services.shared.emails.send_email_change_verification",
        return_value=AsyncMock(),
    )


@pytest.fixture
def mock_shared_send_email_safe(mocker):
    return mocker.patch(
        "src.users.services.shared.emails.send_email_safe",
        new_callable=AsyncMock,
    )


def _current_user(credentials: UserCredentials):
    return SimpleNamespace(
        credentials_id=credentials.id,
        public_id=credentials.public_id,
        role=credentials.role,
        account_type=credentials.account_type,
    )


class TestNoChangesDetected:
    async def test_same_username_raises(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        user = await make_teacher(test_session)
        payload = UpdateUserCredentials(username=user.username)
        current_user = _current_user(user)

        with pytest.raises(NoChangesDetectedError):
            await UserServiceSelf.update_me_credentials(
                test_session, redis_client, current_user, payload
            )

    async def test_same_email_raises(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        user = await make_teacher(test_session)
        payload = UpdateUserCredentials(email=user.email)
        current_user = _current_user(user)

        with pytest.raises(NoChangesDetectedError):
            await UserServiceSelf.update_me_credentials(
                test_session, redis_client, current_user, payload
            )

    async def test_both_same_raises(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        user = await make_teacher(test_session)
        payload = UpdateUserCredentials(username=user.username, email=user.email)
        current_user = _current_user(user)

        with pytest.raises(NoChangesDetectedError):
            await UserServiceSelf.update_me_credentials(
                test_session, redis_client, current_user, payload
            )


class TestUsernameChange:
    async def test_username_updated_in_db(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
    ):
        user = await make_teacher(test_session)
        payload = UpdateUserCredentials(username="newusername1")

        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), payload
        )

        await test_session.refresh(user)
        assert user.username == "newusername1"

    async def test_sessions_invalidated_on_username_change(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
    ):
        user = await make_teacher(test_session)
        session_row = await UserSessionRepository.get_by_credentials_id(
            test_session, user.id
        )
        original_atv = session_row.access_token_version

        payload = UpdateUserCredentials(username="newusername2")

        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), payload
        )

        await test_session.refresh(session_row)
        assert session_row.access_token_version == original_atv + 1
        assert session_row.refresh_token_hash is None
        assert session_row.refresh_token_family is None

    async def test_atv_cache_keys_deleted_on_username_change(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
    ):
        from src.utils.cache_keys import SessionCacheKey

        user = await make_teacher(test_session)
        session_row = await UserSessionRepository.get_by_credentials_id(
            test_session, user.id
        )
        payload = UpdateUserCredentials(username="newusername3")

        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), payload
        )

        call_args = mock_shared_delete_cache.call_args
        deleted_keys = set(call_args.args[1:])
        expected_atv_key = SessionCacheKey.access_token_version_key(session_row.id)
        assert expected_atv_key in deleted_keys

    async def test_no_email_fired_on_username_only_change(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
        mock_shared_send_email_change_verification,
    ):
        user = await make_teacher(test_session)
        payload = UpdateUserCredentials(username="newusername4")

        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), payload
        )

        mock_shared_send_email_change_verification.assert_not_called()

    async def test_duplicate_username_raises(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
    ):
        existing = await make_teacher(test_session)
        user = await make_teacher(test_session)
        payload = UpdateUserCredentials(username=existing.username)

        async def update_user_credentials() -> None:
            await UserServiceSelf.update_me_credentials(
                test_session,
                redis_client,
                _current_user(user),
                payload,
            )

        with pytest.raises(UsernameAlreadyTakenError):
            await update_user_credentials()

    @pytest.mark.db_constraint
    async def test_db_constraint_catches_bypassed_username_precheck(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
        mocker,
    ):
        # No application-level username precheck in this service — the
        # IntegrityError handler IS the only guard, so this test verifies
        # the DB constraint fires and is correctly translated.
        existing = await make_teacher(test_session)
        user = await make_teacher(test_session)

        # Force the username onto the object directly, bypassing any check
        user.username = existing.username

        async def commit_user_changes() -> None:
            await test_session.commit()

        with pytest.raises(UsernameAlreadyTakenError):
            await commit_user_changes()


class TestEmailChange:
    async def test_new_email_change_row_created(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
        mock_shared_send_email_change_verification,
        mock_shared_send_email_safe,
    ):
        user = await make_teacher(test_session)
        new_email = "newemail@meridian.edu"
        payload = UpdateUserCredentials(email=new_email)

        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), payload
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session,
            user.public_id,
            load_options=LoadOptionsSchema(load_email_change=True),
        )
        assert updated.email_change is not None
        assert updated.email_change.new_email == new_email

    async def test_verification_email_fired(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
        mock_shared_send_email_change_verification,
        mock_shared_send_email_safe,
    ):
        user = await make_teacher(test_session)
        new_email = "verify@meridian.edu"
        payload = UpdateUserCredentials(email=new_email)

        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), payload
        )

        mock_shared_send_email_change_verification.assert_called_once()
        call_args = mock_shared_send_email_change_verification.call_args
        assert call_args.args[0] == new_email

    async def test_sessions_not_invalidated_on_email_only_change(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
        mock_shared_send_email_change_verification,
        mock_shared_send_email_safe,
    ):
        user = await make_teacher(test_session)
        session_row = await UserSessionRepository.get_by_credentials_id(
            test_session, user.id
        )
        original_atv = session_row.access_token_version

        payload = UpdateUserCredentials(email="nochange@meridian.edu")

        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), payload
        )

        await test_session.refresh(session_row)
        assert session_row.access_token_version == original_atv

    async def test_atv_cache_keys_not_deleted_on_email_only_change(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
        mock_shared_send_email_change_verification,
        mock_shared_send_email_safe,
    ):
        from src.utils.cache_keys import SessionCacheKey

        user = await make_teacher(test_session)
        session_row = await UserSessionRepository.get_by_credentials_id(
            test_session, user.id
        )
        payload = UpdateUserCredentials(email="noatv@meridian.edu")

        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), payload
        )

        call_args = mock_shared_delete_cache.call_args
        deleted_keys = set(call_args.args[1:])
        unexpected_atv_key = SessionCacheKey.access_token_version_key(session_row.id)
        assert unexpected_atv_key not in deleted_keys

    async def test_existing_email_change_row_overwritten_when_different_email(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
        mock_shared_send_email_change_verification,
        mock_shared_send_email_safe,
    ):
        user = await make_teacher(test_session)

        # First request — creates the row
        first_payload = UpdateUserCredentials(email="first@meridian.edu")
        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), first_payload
        )

        # Second request — different email, should overwrite
        second_payload = UpdateUserCredentials(email="second@meridian.edu")
        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), second_payload
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session,
            user.public_id,
            load_options=LoadOptionsSchema(load_email_change=True),
        )
        assert updated.email_change.new_email == "second@meridian.edu"

    async def test_duplicate_active_pending_request_raises(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
        mock_shared_send_email_change_verification,
        mock_shared_send_email_safe,
    ):
        user = await make_teacher(test_session)

        # First request — creates the row with active expiry
        first_payload = UpdateUserCredentials(email="pending@meridian.edu")
        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), first_payload
        )

        # Second request — same email while still active
        second_payload = UpdateUserCredentials(email="pending@meridian.edu")

        async def update_user_credentials() -> None:
            await UserServiceSelf.update_me_credentials(
                test_session, redis_client, _current_user(user), second_payload
            )

        with pytest.raises(DuplicateEmailChangeRequestError):
            await update_user_credentials()

    async def test_expired_pending_request_overwritten(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
        mock_shared_send_email_change_verification,
        mock_shared_send_email_safe,
    ):
        user = await make_teacher(test_session)

        # Manually insert an expired email_change row for this user
        expired_row = UserEmailChange(
            credentials_id=user.id,
            new_email="expired@meridian.edu",
            email_change_token_hash="oldhash",
            email_change_token_expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        test_session.add(expired_row)
        await test_session.commit()

        # Same email as expired row — should overwrite, not raise
        payload = UpdateUserCredentials(email="expired@meridian.edu")
        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), payload
        )

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session,
            user.public_id,
            load_options=LoadOptionsSchema(load_email_change=True),
        )
        # Row was overwritten with a new token hash
        assert updated.email_change.email_change_token_hash != "oldhash"


class TestBothFields:
    async def test_username_and_email_both_applied(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
        mock_shared_send_email_change_verification,
        mock_shared_send_email_safe,
    ):
        user = await make_teacher(test_session)
        payload = UpdateUserCredentials(
            username="bothfields1",
            email="both@meridian.edu",
        )

        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), payload
        )

        await test_session.refresh(user)
        assert user.username == "bothfields1"

        updated = await UserCredentialsRepository.get_by_public_id(
            test_session,
            user.public_id,
            load_options=LoadOptionsSchema(load_email_change=True),
        )
        assert updated.email_change is not None
        assert updated.email_change.new_email == "both@meridian.edu"

    async def test_sessions_invalidated_and_email_fired_when_both_change(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
        mock_shared_send_email_change_verification,
        mock_shared_send_email_safe,
    ):
        user = await make_teacher(test_session)
        session_row = await UserSessionRepository.get_by_credentials_id(
            test_session, user.id
        )
        original_atv = session_row.access_token_version

        payload = UpdateUserCredentials(
            username="bothfields2",
            email="bothalso@meridian.edu",
        )

        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), payload
        )

        await test_session.refresh(session_row)
        assert session_row.access_token_version == original_atv + 1
        mock_shared_send_email_change_verification.assert_called_once()


class TestCacheKeys:
    async def test_admin_staff_self_keys_always_deleted(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_shared_delete_cache,
    ):
        from src.utils.cache_keys import UserCacheKey

        user = await make_teacher(test_session)
        payload = UpdateUserCredentials(username="cachecheck1")

        await UserServiceSelf.update_me_credentials(
            test_session, redis_client, _current_user(user), payload
        )

        call_args = mock_shared_delete_cache.call_args
        deleted_keys = set(call_args.args[1:])

        assert UserCacheKey.user_detail_key_admin(user.public_id) in deleted_keys
        assert UserCacheKey.user_detail_key_staff(user.public_id) in deleted_keys
        assert UserCacheKey.user_detail_key_self(user.public_id) in deleted_keys
