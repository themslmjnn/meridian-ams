import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.emails.repository import EmailRepository
from src.emails.utils.enums import EmailType
from src.users.models.credentials import UserCredentials
from src.users.models.email_change import UserEmailChange
from src.users.repository.user import (
    UserActivationRepository,
    UserEmailChangeRepository,
    UserSessionRepository,
)
from src.users.services.system_admin import UserService
from src.users.utils.enums import UserStatus
from src.users.utils.exceptions import (
    CredentialsNotFoundError,
    DuplicateEmailError,
    UsernameAlreadyTakenError,
)
from src.users.utils.schemas import UpdateCredentials
from src.utils.exceptions import NoChangesDetectedError
from tests.factories import make_teacher

ENDPOINT = "/api/v1/admin/users"


class TestAdvisoryLock:
    async def test_lock_acquired_when_email_changes(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_advisory_lock_system_admin,
        redis_client,
    ) -> None:
        new_email = "new.teacher@school.com"
        payload = UpdateCredentials(email=new_email)

        await UserService.update_credentials(
            test_session, redis_client, system_admin.id, teacher.public_id, payload
        )

        mock_users_advisory_lock_system_admin.assert_called_once_with(
            test_session,
            phone_number=None,
            email=new_email,
        )

    async def test_no_lock_when_email_unchanged(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_advisory_lock_system_admin,
        redis_client,
    ) -> None:
        payload = UpdateCredentials(
            email=teacher.email,
            username="newusername1",
        )

        await UserService.update_credentials(
            test_session, redis_client, system_admin.id, teacher.public_id, payload
        )

        mock_users_advisory_lock_system_admin.assert_not_called()

    async def test_no_lock_when_email_omitted(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_advisory_lock_system_admin,
        redis_client,
    ) -> None:
        payload = UpdateCredentials(username="newusername2")

        await UserService.update_credentials(
            test_session, redis_client, system_admin.id, teacher.public_id, payload
        )

        mock_users_advisory_lock_system_admin.assert_not_called()


class TestContactLimit:
    async def test_staff_email_change_checked_with_exclusion(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_check_contact_limit_system_admin,
        redis_client,
    ) -> None:
        new_email = "updated.teacher@meridian.edu"
        payload = UpdateCredentials(email=new_email)

        await UserService.update_credentials(
            test_session, redis_client, system_admin.id, teacher.public_id, payload
        )

        mock_users_check_contact_limit_system_admin.assert_called_once_with(
            test_session,
            system_admin.id,
            username=teacher.username,
            phone_number=None,
            email=new_email,
            resolved_role=teacher.role,
            account_type=teacher.account_type,
            exclude_credentials_id=teacher.id,
        )

    async def test_guardian_email_change_checked_with_exclusion(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        guardian: UserCredentials,
        mock_users_check_contact_limit_system_admin,
        redis_client,
    ) -> None:
        new_email = "updated.guardian@example.com"
        payload = UpdateCredentials(email=new_email)

        await UserService.update_credentials(
            test_session, redis_client, system_admin.id, guardian.public_id, payload
        )

        mock_users_check_contact_limit_system_admin.assert_called_once_with(
            test_session,
            system_admin.id,
            username=guardian.username,
            phone_number=None,
            email=new_email,
            resolved_role=guardian.role,
            account_type=guardian.account_type,
            exclude_credentials_id=guardian.id,
        )

    async def test_student_email_change_checked_with_exclusion(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        student: UserCredentials,
        mock_users_check_contact_limit_system_admin,
        redis_client,
    ) -> None:
        new_email = "updated.student@example.com"
        payload = UpdateCredentials(email=new_email)

        await UserService.update_credentials(
            test_session, redis_client, system_admin.id, student.public_id, payload
        )

        mock_users_check_contact_limit_system_admin.assert_called_once_with(
            test_session,
            system_admin.id,
            username=student.username,
            phone_number=None,
            email=new_email,
            resolved_role=student.role,
            account_type=student.account_type,
            exclude_credentials_id=student.id,
        )

    async def test_no_check_when_email_not_changing(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_check_contact_limit_system_admin,
        redis_client,
    ) -> None:
        payload = UpdateCredentials(username="newusername3")

        await UserService.update_credentials(
            test_session, redis_client, system_admin.id, teacher.public_id, payload
        )

        mock_users_check_contact_limit_system_admin.assert_not_called()


class TestNotFound:
    async def test_unknown_public_id_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        redis_client,
    ) -> None:
        payload = UpdateCredentials(username="newusername4")

        with pytest.raises(CredentialsNotFoundError):
            await UserService.update_credentials(
                test_session,
                redis_client,
                system_admin.id,
                uuid.uuid4(),
                payload,
            )

    async def test_system_admin_public_id_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        redis_client,
    ) -> None:
        payload = UpdateCredentials(username="newusername5")

        with pytest.raises(CredentialsNotFoundError):
            await UserService.update_credentials(
                test_session,
                redis_client,
                system_admin.id,
                system_admin.public_id,
                payload,
            )


class TestNoChanges:
    async def test_same_username_and_email_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        redis_client,
    ) -> None:
        payload = UpdateCredentials(
            username=teacher.username,
            email=teacher.email,
        )

        with pytest.raises(NoChangesDetectedError):
            await UserService.update_credentials(
                test_session,
                redis_client,
                system_admin.id,
                teacher.public_id,
                payload,
            )


class TestActivationTokenReissue:
    async def test_pending_user_email_change_reissues_activation_token(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        mock_users_advisory_lock_system_admin,
        redis_client,
    ) -> None:
        pending_teacher = await make_teacher(
            test_session, status=UserStatus.PENDING_ACTIVATION
        )
        user_activation = await UserActivationRepository.get_by_id(
            test_session, pending_teacher.id
        )
        old_token_hash = user_activation.activation_token_hash
        payload = UpdateCredentials(email="reissued.teacher@meridian.edu")

        await UserService.update_credentials(
            test_session,
            redis_client,
            system_admin.id,
            pending_teacher.public_id,
            payload,
        )

        new_user_activation = await UserActivationRepository.get_by_id(
            test_session, pending_teacher.id
        )

        assert new_user_activation.activation_token_hash != old_token_hash
        assert new_user_activation.activation_token_expires_at > datetime.now(UTC)

    async def test_pending_user_email_change_queues_activation_email(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        mock_users_advisory_lock_system_admin,
        redis_client,
    ) -> None:
        pending_teacher = await make_teacher(
            test_session, status=UserStatus.PENDING_ACTIVATION
        )
        new_email = "reissued2.teacher@meridian.edu"
        payload = UpdateCredentials(email=new_email)

        await UserService.update_credentials(
            test_session,
            redis_client,
            system_admin.id,
            pending_teacher.public_id,
            payload,
        )

        emails = await EmailRepository.get_by_triggered_by(
            test_session, system_admin.id
        )

        assert emails is not None
        assert emails[0].triggered_by == system_admin.id

    async def test_active_user_email_change_does_not_reissue_token(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_advisory_lock_system_admin,
        redis_client,
    ) -> None:
        payload = UpdateCredentials(email="active.new@meridian.edu")

        await UserService.update_credentials(
            test_session,
            redis_client,
            system_admin.id,
            teacher.public_id,
            payload,
        )

        emails = await EmailRepository.get_by_triggered_by(
            test_session, system_admin.id
        )

        assert emails is not None
        assert emails[0].email_type != EmailType.ACTIVATION


class TestNotificationEmail:
    async def test_username_change_queues_notification_to_old_email(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        redis_client,
    ) -> None:
        old_email = teacher.email
        payload = UpdateCredentials(username="brandnewuser1")

        await UserService.update_credentials(
            test_session,
            redis_client,
            system_admin.id,
            teacher.public_id,
            payload,
        )

        emails = await EmailRepository.get_by_triggered_by(
            test_session, system_admin.id
        )

        assert emails is not None
        assert emails[0].email_type == EmailType.ADMIN_CREDENTIALS_OVERRIDE
        assert emails[0].recipient_email == old_email

    async def test_email_change_queues_notification_to_old_email(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_advisory_lock_system_admin,
        redis_client,
    ) -> None:
        old_email = teacher.email
        payload = UpdateCredentials(email="changed.teacher@meridian.edu")

        await UserService.update_credentials(
            test_session,
            redis_client,
            system_admin.id,
            teacher.public_id,
            payload,
        )

        emails = await EmailRepository.get_by_triggered_by(
            test_session, system_admin.id
        )

        assert emails is not None
        assert emails[0].email_type == EmailType.ADMIN_CREDENTIALS_OVERRIDE
        assert emails[0].recipient_email == old_email

    async def test_both_changed_queues_single_notification(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_advisory_lock_system_admin,
        redis_client,
    ) -> None:
        old_email = teacher.email
        payload = UpdateCredentials(
            username="brandnewuser2",
            email="both.changed@meridian.edu",
        )

        await UserService.update_credentials(
            test_session,
            redis_client,
            system_admin.id,
            teacher.public_id,
            payload,
        )

        emails = await EmailRepository.get_by_triggered_by(
            test_session, system_admin.id
        )

        assert len(emails) == 1
        assert emails[0].email_type == EmailType.ADMIN_CREDENTIALS_OVERRIDE
        assert emails[0].recipient_email == old_email


class TestPendingEmailChangeCleared:
    async def test_email_change_row_deleted_on_credentials_update(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        mock_users_advisory_lock_system_admin,
        redis_client,
    ) -> None:
        teacher = await make_teacher(test_session)
        email_change = UserEmailChange(
            credentials_id=teacher.id,
            new_email="pending@school.com",
            email_change_token_hash="somehash",
            email_change_token_expires_at=datetime.now(UTC),
        )
        test_session.add(email_change)
        await test_session.flush()

        payload = UpdateCredentials(username="cleanedup1")

        await UserService.update_credentials(
            test_session,
            redis_client,
            system_admin.id,
            teacher.public_id,
            payload,
        )

        user_email_change = await UserEmailChangeRepository.get_by_id(
            test_session, teacher.id
        )

        assert user_email_change is None


class TestSessionsInvalidated:
    async def test_all_sessions_invalidated_on_username_change(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        redis_client,
    ) -> None:
        user_session = await UserSessionRepository.get_by_credentials_id(
            test_session, teacher.id
        )
        old_atv = user_session.access_token_version

        payload = UpdateCredentials(username="brandnewuser3")

        await UserService.update_credentials(
            test_session,
            redis_client,
            system_admin.id,
            teacher.public_id,
            payload,
        )

        user_session_after = await UserSessionRepository.get_by_credentials_id(
            test_session, teacher.id
        )

        assert user_session_after.access_token_version == old_atv + 1
        assert user_session_after.refresh_token_hash is None
        assert user_session_after.refresh_token_family is None

    async def test_all_sessions_invalidated_on_email_change(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_advisory_lock_system_admin,
        redis_client,
    ) -> None:
        user_session = await UserSessionRepository.get_by_credentials_id(
            test_session, teacher.id
        )
        old_atv = user_session.access_token_version

        payload = UpdateCredentials(email="sessions.cleared@school.com")

        await UserService.update_credentials(
            test_session,
            redis_client,
            system_admin.id,
            teacher.public_id,
            payload,
        )

        user_session_after = await UserSessionRepository.get_by_credentials_id(
            test_session, teacher.id
        )

        assert user_session_after.access_token_version == old_atv + 1


class TestCacheInvalidated:
    async def test_cache_deleted_on_success(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_delete_cache_system_admin,
        redis_client,
    ) -> None:
        payload = UpdateCredentials(username="brandnewuser4")

        await UserService.update_credentials(
            test_session,
            redis_client,
            system_admin.id,
            teacher.public_id,
            payload,
        )

        mock_users_delete_cache_system_admin.assert_called_once()


class TestDBConstraints:
    @pytest.mark.db_constraint
    async def test_duplicate_username_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        redis_client,
        mock_users_check_contact_limit_system_admin,
    ) -> None:
        existing = await make_teacher(test_session, username="takenusername1")

        payload = UpdateCredentials(username=existing.username)

        with pytest.raises(UsernameAlreadyTakenError):
            await UserService.update_credentials(
                test_session,
                redis_client,
                system_admin.id,
                teacher.public_id,
                payload,
            )

    @pytest.mark.db_constraint
    async def test_non_student_duplicate_email_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_advisory_lock_system_admin,
        redis_client,
        mock_users_check_contact_limit_system_admin,
    ) -> None:
        existing = await make_teacher(test_session)

        payload = UpdateCredentials(email=existing.email)

        with pytest.raises(DuplicateEmailError):
            await UserService.update_credentials(
                test_session,
                redis_client,
                system_admin.id,
                teacher.public_id,
                payload,
            )
