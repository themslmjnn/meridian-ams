import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppException
from src.users.models.credentials import UserCredentials
from src.users.schemas.system_admin import (
    CreateGuardianWithExistingIdentity,
    CreateGuardianWithNewIdentity,
    CreateStaff,
    CreateStudent,
)
from src.users.services.system_admin import UserService
from src.users.utils.exceptions import (
    DuplicateEmailError,
    DuplicatePhoneNumberError,
    MaxStudentsPerEmailError,
    MaxStudentsPerPhoneNumberError,
)
from tests.factories import make_guardian, make_student, make_teacher


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


class TestContactLimit:
    @pytest.mark.parametrize(
        ("field", "value", "expected_exception"),
        [
            ("phone_number", "+992555000001", MaxStudentsPerPhoneNumberError),
            ("email", "shared.student@example.com", MaxStudentsPerEmailError),
        ],
    )
    async def test_student_rejected_when_contact_limit_reached(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        valid_student_payload: CreateStudent,
        field: str,
        value: str,
        expected_exception: type[AppException],
    ) -> None:
        for i in range(3):
            await make_student(
                test_session,
                username=f"limit_student_{i}",
                **{field: value},
            )

        setattr(valid_student_payload, field, value)

        with pytest.raises(expected_exception):
            await UserService.register_user(
                test_session, system_admin.id, valid_student_payload
            )

    @pytest.mark.parametrize(
        ("factory", "field", "value", "expected_exception"),
        [
            (make_teacher, "phone_number", "+992555000002", DuplicatePhoneNumberError),
            (make_teacher, "email", "shared.staff@example.com", DuplicateEmailError),
            (make_guardian, "phone_number", "+992555000003", DuplicatePhoneNumberError),
            (
                make_guardian,
                "email",
                "shared.guardian@example.com",
                DuplicateEmailError,
            ),
        ],
    )
    async def test_staff_and_guardian_rejected_when_contact_limit_reached(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
        valid_new_guardian_payload: CreateGuardianWithNewIdentity,
        factory,
        field: str,
        value: str,
        expected_exception: type[AppException],
    ) -> None:
        await factory(test_session, **{field: value})

        payload = (
            valid_staff_payload
            if factory is make_teacher
            else valid_new_guardian_payload
        )
        setattr(payload, field, value)

        with pytest.raises(expected_exception):
            await UserService.register_user(test_session, system_admin.id, payload)
