import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserIdentityRepository
from src.users.schemas.guardian import UpdateProfileGuardian
from src.users.services.guardian import UserServiceGuardian
from src.users.utils.exceptions import DuplicatePhoneNumberError
from src.utils.exceptions import NoChangesDetectedError
from tests.factories import make_guardian

PROFILE_ENDPOINT = "/api/v1/users/me/profile"


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


class TestAdvisoryLock:
    async def test_lock_acquired_when_phone_changes(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_advisory_lock,
        mock_guardian_check_contact_limit,
        mock_guardian_delete_cache,
        mock_guardian_send_info_updated_email,
    ):
        user = await make_guardian(test_session)

        new_phone = "+992999000001"
        payload = UpdateProfileGuardian(phone_number=new_phone)

        await UserServiceGuardian.update_me_profile(
            test_session, redis_client, _make_current_user(user), payload
        )

        mock_guardian_advisory_lock.assert_called_once_with(
            test_session,
            phone_number=new_phone,
            email=None,
        )

    async def test_no_lock_when_phone_unchanged(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_advisory_lock,
        mock_guardian_check_contact_limit,
        mock_guardian_delete_cache,
        mock_guardian_send_info_updated_email,
    ):
        user = await make_guardian(test_session)

        identity = await UserIdentityRepository.get_by_id(
            test_session, user.identity_id
        )
        payload = UpdateProfileGuardian(phone_number=identity.phone_number)
        current_user = _make_current_user(user)

        with pytest.raises(NoChangesDetectedError):
            await UserServiceGuardian.update_me_profile(
                test_session, redis_client, current_user, payload
            )

        mock_guardian_advisory_lock.assert_not_called()

    async def test_no_lock_when_phone_not_provided(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_advisory_lock,
        mock_guardian_check_contact_limit,
        mock_guardian_delete_cache,
        mock_guardian_send_info_updated_email,
    ):
        user = await make_guardian(test_session)
        payload = UpdateProfileGuardian(firstname="Newname")

        await UserServiceGuardian.update_me_profile(
            test_session, redis_client, _make_current_user(user), payload
        )

        mock_guardian_advisory_lock.assert_not_called()


class TestSuccess:
    async def test_firstname_updated(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_advisory_lock,
        mock_guardian_check_contact_limit,
        mock_guardian_delete_cache,
        mock_guardian_send_info_updated_email,
    ):
        user = await make_guardian(test_session)
        payload = UpdateProfileGuardian(firstname="Updated")

        await UserServiceGuardian.update_me_profile(
            test_session, redis_client, _make_current_user(user), payload
        )

        identity = await UserIdentityRepository.get_by_id(
            test_session, user.identity_id
        )
        assert identity.firstname == "Updated"

    async def test_lastname_updated(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_advisory_lock,
        mock_guardian_check_contact_limit,
        mock_guardian_delete_cache,
        mock_guardian_send_info_updated_email,
    ):
        user = await make_guardian(test_session)
        payload = UpdateProfileGuardian(lastname="Newsurname")

        await UserServiceGuardian.update_me_profile(
            test_session, redis_client, _make_current_user(user), payload
        )

        identity = await UserIdentityRepository.get_by_id(
            test_session, user.identity_id
        )
        assert identity.lastname == "Newsurname"

    async def test_phone_number_updated(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_advisory_lock,
        mock_guardian_check_contact_limit,
        mock_guardian_delete_cache,
        mock_guardian_send_info_updated_email,
    ):
        user = await make_guardian(test_session)
        new_phone = "+992999000002"
        payload = UpdateProfileGuardian(phone_number=new_phone)

        await UserServiceGuardian.update_me_profile(
            test_session, redis_client, _make_current_user(user), payload
        )

        identity = await UserIdentityRepository.get_by_id(
            test_session, user.identity_id
        )
        assert identity.phone_number == new_phone

    async def test_cache_deleted(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_advisory_lock,
        mock_guardian_check_contact_limit,
        mock_guardian_delete_cache,
        mock_guardian_send_info_updated_email,
    ):
        user = await make_guardian(test_session)
        payload = UpdateProfileGuardian(firstname="Cached")

        await UserServiceGuardian.update_me_profile(
            test_session, redis_client, _make_current_user(user), payload
        )

        mock_guardian_delete_cache.assert_called_once()

    async def test_info_updated_email_fired(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_advisory_lock,
        mock_guardian_check_contact_limit,
        mock_guardian_delete_cache,
        mock_send_account_info_updated_email,
    ):

        user = await make_guardian(test_session)
        payload = UpdateProfileGuardian(firstname="Emailed")

        await UserServiceGuardian.update_me_profile(
            test_session, redis_client, _make_current_user(user), payload
        )

        mock_send_account_info_updated_email.assert_called_once_with(user.email)


class TestContactLimit:
    async def test_duplicate_phone_rejected(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        mock_guardian_delete_cache,
        mock_guardian_send_info_updated_email,
    ):
        await make_guardian(test_session, phone_number="+992555000010")
        user = await make_guardian(test_session)
        payload = UpdateProfileGuardian(phone_number="+992555000010")
        current_user = _make_current_user(user)

        with pytest.raises(DuplicatePhoneNumberError):
            await UserServiceGuardian.update_me_profile(
                test_session, redis_client, current_user, payload
            )


def _make_current_user(credentials: UserCredentials):
    """
    Build a minimal CurrentUser-like object from a UserCredentials instance.
    Avoids going through login just to get a current_user context for service calls.
    """
    from types import SimpleNamespace

    return SimpleNamespace(
        credentials_id=credentials.id,
        public_id=credentials.public_id,
        role=credentials.role,
        account_type=credentials.account_type,
    )
