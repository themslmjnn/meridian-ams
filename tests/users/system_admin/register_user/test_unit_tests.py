from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.schemas.system_admin import (
    CreateGuardianWithExistingIdentity,
    CreateGuardianWithNewIdentity,
    CreateStaff,
    CreateStudent,
)
from src.users.services.system_admin import UserService


class TestAdvisoryLock:
    async def test_student_acquires_phone_and_email_lock(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        valid_student_payload: CreateStudent,
        mock_users_advisory_lock_system_admin,
    ) -> None:
        await UserService.register_user(
            test_session, system_admin.id, valid_student_payload
        )

        mock_users_advisory_lock_system_admin.assert_called_once_with(
            test_session,
            phone_number=valid_student_payload.phone_number,
            email=valid_student_payload.email,
        )

    async def test_staff_acquires_phone_and_email_lock(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
        mock_users_advisory_lock_system_admin,
    ) -> None:
        await UserService.register_user(
            test_session, system_admin.id, valid_staff_payload
        )

        mock_users_advisory_lock_system_admin.assert_called_once_with(
            test_session,
            phone_number=valid_staff_payload.phone_number,
            email=valid_staff_payload.email,
        )

    async def test_new_guardian_acquires_phone_and_email_lock(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        valid_new_guardian_payload: CreateGuardianWithNewIdentity,
        mock_users_advisory_lock_system_admin,
    ) -> None:
        await UserService.register_user(
            test_session, system_admin.id, valid_new_guardian_payload
        )

        mock_users_advisory_lock_system_admin.assert_called_once_with(
            test_session,
            phone_number=valid_new_guardian_payload.phone_number,
            email=valid_new_guardian_payload.email,
        )

    async def test_existing_guardian_acquires_email_lock_only(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        valid_existing_guardian_payload: CreateGuardianWithExistingIdentity,
        mock_users_advisory_lock_system_admin,
    ) -> None:
        await UserService.register_user(
            test_session, system_admin.id, valid_existing_guardian_payload
        )

        mock_users_advisory_lock_system_admin.assert_called_once_with(
            test_session,
            phone_number=None,
            email=valid_existing_guardian_payload.email,
        )
