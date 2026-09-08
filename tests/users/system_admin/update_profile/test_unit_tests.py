import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserIdentityRepository
from src.users.schemas.system_admin import (
    UpdateStaffOrGuardianProfile,
    UpdateStudentProfile,
)
from src.users.services.system_admin import UserService
from src.users.utils.exceptions import (
    CredentialsNotFoundError,
    UpdatePayloadMismatchError,
)
from src.utils.exceptions import NoChangesDetectedError

STAFF_GUARDIAN_UPDATE = UpdateStaffOrGuardianProfile(
    type="staff_or_guardian",
    firstname="Updated",
    lastname="Name",
)

STUDENT_UPDATE = UpdateStudentProfile(
    type="student",
    firstname="Updated",
    lastname="Name",
)


class TestAdvisoryLock:
    async def test_lock_acquired_when_phone_number_changes(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_advisory_lock_system_admin,
        redis_client,
    ) -> None:
        new_phone = "+992555999001"
        payload = UpdateStaffOrGuardianProfile(
            type="staff_or_guardian",
            phone_number=new_phone,
        )

        await UserService.update_profile(
            test_session, redis_client, system_admin.id, teacher.public_id, payload
        )

        mock_users_advisory_lock_system_admin.assert_called_once_with(
            test_session,
            phone_number=new_phone,
            email=None,
        )

    async def test_no_lock_when_phone_number_unchanged(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_advisory_lock_system_admin,
        redis_client,
    ) -> None:
        user_identity = await UserIdentityRepository.get_by_id(
            test_session, teacher.identity_id
        )
        payload = UpdateStaffOrGuardianProfile(
            type="staff_or_guardian",
            phone_number=user_identity.phone_number,
            firstname="Updated",
        )

        await UserService.update_profile(
            test_session, redis_client, system_admin.id, teacher.public_id, payload
        )

        mock_users_advisory_lock_system_admin.assert_called_once_with(
            test_session,
            phone_number=None,
            email=None,
        )

    async def test_no_lock_when_phone_number_omitted(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_advisory_lock_system_admin,
        redis_client,
    ) -> None:
        payload = UpdateStaffOrGuardianProfile(
            type="staff_or_guardian",
            firstname="Updated",
        )

        await UserService.update_profile(
            test_session, redis_client, system_admin.id, teacher.public_id, payload
        )

        mock_users_advisory_lock_system_admin.assert_called_once_with(
            test_session,
            phone_number=None,
            email=None,
        )


class TestContactLimit:
    async def test_staff_phone_change_checked_with_exclusion(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_check_contact_limit_system_admin,
        redis_client,
    ) -> None:
        new_phone = "+992555999002"
        payload = UpdateStaffOrGuardianProfile(
            type="staff_or_guardian",
            phone_number=new_phone,
        )

        await UserService.update_profile(
            test_session, redis_client, system_admin.id, teacher.public_id, payload
        )

        mock_users_check_contact_limit_system_admin.assert_called_once_with(
            test_session,
            system_admin.id,
            username=teacher.username,
            phone_number=new_phone,
            email=None,
            resolved_role=teacher.role,
            account_type=teacher.account_type,
            exclude_credentials_id=teacher.id,
        )

    async def test_guardian_phone_change_checked_with_exclusion(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        guardian: UserCredentials,
        mock_users_check_contact_limit_system_admin,
        redis_client,
    ) -> None:
        new_phone = "+992555999003"
        payload = UpdateStaffOrGuardianProfile(
            type="staff_or_guardian",
            phone_number=new_phone,
        )

        await UserService.update_profile(
            test_session, redis_client, system_admin.id, guardian.public_id, payload
        )

        mock_users_check_contact_limit_system_admin.assert_called_once_with(
            test_session,
            system_admin.id,
            username=guardian.username,
            phone_number=new_phone,
            email=None,
            resolved_role=guardian.role,
            account_type=guardian.account_type,
            exclude_credentials_id=guardian.id,
        )

    async def test_student_phone_change_checked_with_exclusion(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        student: UserCredentials,
        mock_users_check_contact_limit_system_admin,
        redis_client,
    ) -> None:
        new_phone = "+992555999004"
        payload = UpdateStudentProfile(
            type="student",
            phone_number=new_phone,
        )

        await UserService.update_profile(
            test_session, redis_client, system_admin.id, student.public_id, payload
        )

        mock_users_check_contact_limit_system_admin.assert_called_once_with(
            test_session,
            system_admin.id,
            username=student.username,
            phone_number=new_phone,
            email=None,
            resolved_role=student.role,
            account_type=student.account_type,
            exclude_credentials_id=student.id,
        )

    async def test_contact_limit_not_checked_when_phone_omitted(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_check_contact_limit_system_admin,
        redis_client,
    ) -> None:
        payload = UpdateStaffOrGuardianProfile(
            type="staff_or_guardian",
            firstname="Updated",
        )

        await UserService.update_profile(
            test_session, redis_client, system_admin.id, teacher.public_id, payload
        )

        mock_users_check_contact_limit_system_admin.assert_called_once_with(
            test_session,
            system_admin.id,
            username=teacher.username,
            phone_number=None,
            email=None,
            resolved_role=teacher.role,
            account_type=teacher.account_type,
            exclude_credentials_id=teacher.id,
        )


class TestPayloadMismatch:
    async def test_student_payload_for_staff_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        redis_client,
    ) -> None:
        payload = UpdateStudentProfile(type="student", firstname="Updated")

        with pytest.raises(UpdatePayloadMismatchError):
            await UserService.update_profile(
                test_session, redis_client, system_admin.id, teacher.public_id, payload
            )

    async def test_student_payload_for_guardian_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        guardian: UserCredentials,
        redis_client,
    ) -> None:
        payload = UpdateStudentProfile(type="student", firstname="Updated")

        with pytest.raises(UpdatePayloadMismatchError):
            await UserService.update_profile(
                test_session,
                redis_client,
                system_admin.id,
                guardian.public_id,
                payload,
            )

    async def test_staff_payload_for_student_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        student: UserCredentials,
        redis_client,
    ) -> None:
        payload = UpdateStaffOrGuardianProfile(
            type="staff_or_guardian", firstname="Updated"
        )

        with pytest.raises(UpdatePayloadMismatchError):
            await UserService.update_profile(
                test_session, redis_client, system_admin.id, student.public_id, payload
            )


class TestNotFound:
    async def test_unknown_public_id_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        redis_client,
    ) -> None:
        with pytest.raises(CredentialsNotFoundError):
            await UserService.update_profile(
                test_session,
                redis_client,
                system_admin.id,
                uuid.uuid4(),
                STAFF_GUARDIAN_UPDATE,
            )

    async def test_system_admin_public_id_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        redis_client,
    ) -> None:
        with pytest.raises(CredentialsNotFoundError):
            await UserService.update_profile(
                test_session,
                redis_client,
                system_admin.id,
                system_admin.public_id,
                STAFF_GUARDIAN_UPDATE,
            )


class TestNoChanges:
    async def test_same_values_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        redis_client,
    ) -> None:
        user_identity = await UserIdentityRepository.get_by_id(
            test_session, teacher.identity_id
        )
        payload = UpdateStaffOrGuardianProfile(
            type="staff_or_guardian",
            firstname=user_identity.firstname,
            lastname=user_identity.lastname,
        )

        with pytest.raises(NoChangesDetectedError):
            await UserService.update_profile(
                test_session, redis_client, system_admin.id, teacher.public_id, payload
            )


class TestSuccessUpdate:
    async def test_staff_fields_updated(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_delete_cache_system_admin,
        redis_client,
    ) -> None:
        payload = UpdateStaffOrGuardianProfile(
            type="staff_or_guardian",
            firstname="UpdatedFirst",
            lastname="UpdatedLast",
            phone_number="+992555888001",
        )

        await UserService.update_profile(
            test_session, redis_client, system_admin.id, teacher.public_id, payload
        )

        identity = await UserIdentityRepository.get_by_id(
            test_session, teacher.identity_id
        )

        assert identity.firstname == "Updatedfirst"
        assert identity.lastname == "Updatedlast"
        assert identity.phone_number == "+992555888001"

    async def test_student_fields_updated(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        student: UserCredentials,
        mock_users_delete_cache_system_admin,
        redis_client,
    ) -> None:
        from datetime import date

        payload = UpdateStudentProfile(
            type="student",
            firstname="UpdatedFirst",
            lastname="UpdatedLast",
            date_of_birth=date(2007, 6, 15),
            address="123 Updated Street, City",
        )

        await UserService.update_profile(
            test_session, redis_client, system_admin.id, student.public_id, payload
        )

        identity = await UserIdentityRepository.get_by_id(
            test_session, student.identity_id
        )

        assert identity.firstname == "Updatedfirst"
        assert identity.lastname == "Updatedlast"
        assert identity.date_of_birth == date(2007, 6, 15)
        assert identity.address == "123 Updated Street, City"

    async def test_guardian_fields_updated(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        guardian: UserCredentials,
        mock_users_delete_cache_system_admin,
        redis_client,
    ) -> None:
        payload = UpdateStaffOrGuardianProfile(
            type="staff_or_guardian",
            firstname="UpdatedFirst",
            lastname="UpdatedLast",
        )

        await UserService.update_profile(
            test_session, redis_client, system_admin.id, guardian.public_id, payload
        )

        identity = await UserIdentityRepository.get_by_id(
            test_session, guardian.identity_id
        )

        assert identity.firstname == "Updatedfirst"
        assert identity.lastname == "Updatedlast"

    async def test_cache_invalidated_on_success(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_delete_cache_system_admin,
        redis_client,
    ) -> None:
        payload = UpdateStaffOrGuardianProfile(
            type="staff_or_guardian",
            firstname="UpdatedFirst",
        )

        await UserService.update_profile(
            test_session, redis_client, system_admin.id, teacher.public_id, payload
        )

        mock_users_delete_cache_system_admin.assert_called_once()

    async def test_email_fired_on_success(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        mock_users_delete_cache_system_admin,
        redis_client,
        mock_send_account_info_updated_email,
    ) -> None:
        payload = UpdateStaffOrGuardianProfile(
            type="staff_or_guardian",
            firstname="UpdatedFirst",
        )

        await UserService.update_profile(
            test_session, redis_client, system_admin.id, teacher.public_id, payload
        )

        mock_send_account_info_updated_email.assert_called_once()
