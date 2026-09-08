import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppException
from src.emails.repository import EmailRepository
from src.emails.utils.enums import EmailType
from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserCredentialsRepository, UserIdentityRepository
from src.users.schemas.system_admin import (
    CreateGuardianWithExistingIdentity,
    CreateGuardianWithNewIdentity,
    CreateStaff,
    CreateStudent,
)
from src.users.services.system_admin import UserService
from src.users.utils.enums import AccountType, UserRole, UserStatus
from src.users.utils.exceptions import (
    DuplicateEmailError,
    DuplicatePhoneNumberError,
    GuardianAccountAlreadyExistsError,
    IdentityNotFoundError,
    MaxStudentsPerEmailError,
    MaxStudentsPerPhoneNumberError,
    UsernameAlreadyTakenError,
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


class TestDuplicateFieldRejection:
    @pytest.mark.parametrize(
        ("existing_kwargs", "override", "expected_exception"),
        [
            (
                {"username": "taken_username"},
                {"username": "taken_username"},
                UsernameAlreadyTakenError,
            ),
            (
                {"phone_number": "+992555111222"},
                {"phone_number": "+992555111222"},
                DuplicatePhoneNumberError,
            ),
            (
                {"email": "taken.staff@example.com"},
                {"email": "taken.staff@example.com"},
                DuplicateEmailError,
            ),
        ],
    )
    async def test_staff_duplicate_fields_rejected(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
        existing_kwargs: dict,
        override: dict,
        expected_exception: type[Exception],
    ) -> None:
        await make_teacher(test_session, **existing_kwargs)

        for field, value in override.items():
            setattr(valid_staff_payload, field, value)

        with pytest.raises(expected_exception):
            await UserService.register_user(
                test_session, system_admin.id, valid_staff_payload
            )

    @pytest.mark.parametrize(
        ("existing_kwargs", "override", "expected_exception"),
        [
            (
                {"username": "taken_username"},
                {"username": "taken_username"},
                UsernameAlreadyTakenError,
            ),
            (
                {"phone_number": "+992555111333"},
                {"phone_number": "+992555111333"},
                MaxStudentsPerPhoneNumberError,
            ),
            (
                {"email": "taken.student@example.com"},
                {"email": "taken.student@example.com"},
                MaxStudentsPerEmailError,
            ),
        ],
    )
    async def test_student_duplicate_fields_rejected(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        valid_student_payload: CreateStudent,
        existing_kwargs: dict,
        override: dict,
        expected_exception: type[Exception],
    ) -> None:
        count = 1 if "username" in existing_kwargs else 3

        for i in range(count):
            if count == 3:
                existing_kwargs["username"] = f"existing_student_{i}"

            await make_student(
                test_session,
                **existing_kwargs,
            )

        for field, value in override.items():
            setattr(valid_student_payload, field, value)

        with pytest.raises(expected_exception):
            await UserService.register_user(
                test_session, system_admin.id, valid_student_payload
            )

    @pytest.mark.parametrize(
        ("existing_kwargs", "override", "expected_exception"),
        [
            (
                {"username": "taken_username"},
                {"username": "taken_username"},
                UsernameAlreadyTakenError,
            ),
            (
                {"phone_number": "+992555111444"},
                {"phone_number": "+992555111444"},
                DuplicatePhoneNumberError,
            ),
            (
                {"email": "taken.guardian@example.com"},
                {"email": "taken.guardian@example.com"},
                DuplicateEmailError,
            ),
        ],
    )
    async def test_guardian_duplicate_fields_rejected(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        valid_new_guardian_payload: CreateGuardianWithNewIdentity,
        existing_kwargs: dict,
        override: dict,
        expected_exception: type[Exception],
    ) -> None:
        await make_guardian(test_session, **existing_kwargs)

        for field, value in override.items():
            setattr(valid_new_guardian_payload, field, value)

        with pytest.raises(expected_exception):
            await UserService.register_user(
                test_session, system_admin.id, valid_new_guardian_payload
            )


class TestDBConstraints:
    @pytest.mark.db_constraint
    @pytest.mark.parametrize(
        (
            "factory",
            "payload_fixture",
            "existing_kwargs",
            "override",
            "expected_exception",
        ),
        [
            (
                make_teacher,
                "valid_staff_payload",
                {"username": "test_staff"},
                {"username": "test_staff"},
                UsernameAlreadyTakenError,
            ),
            (
                make_teacher,
                "valid_staff_payload",
                {"email": "constraint.staff@example.com"},
                {"email": "constraint.staff@example.com"},
                DuplicateEmailError,
            ),
            (
                make_guardian,
                "valid_new_guardian_payload",
                {"username": "test_guardian"},
                {"username": "test_guardian"},
                UsernameAlreadyTakenError,
            ),
            (
                make_guardian,
                "valid_new_guardian_payload",
                {"email": "constraint.guardian@example.com"},
                {"email": "constraint.guardian@example.com"},
                DuplicateEmailError,
            ),
        ],
        ids=[
            "staff_phone",
            "staff_email",
            "guardian_phone",
            "guardian_email",
        ],
    )
    async def test_db_constraint_catches_bypassed_precheck(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        factory,
        payload_fixture: str,
        existing_kwargs: dict,
        override: dict,
        expected_exception: type[Exception],
        request: pytest.FixtureRequest,
        mock_users_check_contact_limit_system_admin,
    ) -> None:
        await factory(test_session, **existing_kwargs)

        payload = request.getfixturevalue(payload_fixture)
        for field, value in override.items():
            setattr(payload, field, value)

        with pytest.raises(expected_exception):
            await UserService.register_user(test_session, system_admin.id, payload)


class TestExistingIdentityGuardian:
    async def test_reuses_existing_identity_row(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        existing_identity: UserCredentials,
        valid_existing_guardian_payload: CreateGuardianWithExistingIdentity,
    ) -> None:
        identity_count_before = await UserIdentityRepository.count_identities(
            test_session, existing_identity.id
        )

        await UserService.register_user(
            test_session, system_admin.id, valid_existing_guardian_payload
        )

        identity_count_after = await UserIdentityRepository.count_identities(
            test_session, existing_identity.id
        )

        assert identity_count_after == identity_count_before

    async def test_creates_new_credentials_row(
        self,
        test_session: AsyncSession,
        registered_existing_guardian: UserCredentials,
    ) -> None:
        credentials_rows = await UserCredentialsRepository.count_credentials(
            test_session, registered_existing_guardian.identity_id
        )

        assert credentials_rows == 2

    async def test_raises_when_identity_not_found(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
    ) -> None:
        payload = CreateGuardianWithExistingIdentity(
            type="existing_guardian",
            existing_identity_id=999999,
            username="ghost_guardian",
            email="ghost@example.com",
        )

        with pytest.raises(IdentityNotFoundError):
            await UserService.register_user(test_session, system_admin.id, payload)

    async def test_raises_when_guardian_account_already_exists(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        existing_identity: UserCredentials,
        valid_existing_guardian_payload: CreateGuardianWithExistingIdentity,
    ) -> None:
        await UserService.register_user(
            test_session, system_admin.id, valid_existing_guardian_payload
        )

        second_payload = CreateGuardianWithExistingIdentity(
            type="existing_guardian",
            existing_identity_id=existing_identity.identity_id,
            username="second_guardian_user",
            email="second.guardian@example.com",
        )

        with pytest.raises(GuardianAccountAlreadyExistsError):
            await UserService.register_user(
                test_session, system_admin.id, second_payload
            )


class TestActivationRow:
    async def test_staff_activation_row_created(
        self, registered_staff: UserCredentials
    ) -> None:
        activation = registered_staff.activation

        assert activation is not None
        assert activation.credentials_id == registered_staff.id
        assert activation.activation_token_hash is not None
        assert activation.activation_token_expires_at is not None

    async def test_student_activation_row_created(
        self, registered_student: UserCredentials
    ) -> None:
        activation = registered_student.activation

        assert activation is not None
        assert activation.credentials_id == registered_student.id
        assert activation.activation_token_hash is not None
        assert activation.activation_token_expires_at is not None

    async def test_new_guardian_activation_row_created(
        self, registered_new_guardian: UserCredentials
    ) -> None:
        activation = registered_new_guardian.activation

        assert activation is not None
        assert activation.credentials_id == registered_new_guardian.id
        assert activation.activation_token_hash is not None
        assert activation.activation_token_expires_at is not None


class TestLoginLockoutRow:
    async def test_staff_lockout_row_created(
        self, registered_staff: UserCredentials
    ) -> None:
        lockout = registered_staff.login_lockout

        assert lockout is not None
        assert lockout.credentials_id == registered_staff.id
        assert lockout.failed_attempts == 0
        assert lockout.locked_until is None

    async def test_student_lockout_row_created(
        self, registered_student: UserCredentials
    ) -> None:
        lockout = registered_student.login_lockout

        assert lockout is not None
        assert lockout.credentials_id == registered_student.id
        assert lockout.failed_attempts == 0
        assert lockout.locked_until is None

    async def test_new_guardian_lockout_row_created(
        self, registered_new_guardian: UserCredentials
    ) -> None:
        lockout = registered_new_guardian.login_lockout

        assert lockout is not None
        assert lockout.credentials_id == registered_new_guardian.id
        assert lockout.failed_attempts == 0
        assert lockout.locked_until is None


class TestEmailRow:
    async def test_staff_activation_email_queued(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        registered_staff: UserCredentials,
    ) -> None:
        emails = await EmailRepository.get_by_triggered_by(
            test_session, system_admin.id
        )

        assert len(emails) == 1
        assert emails[0].recipient_email == registered_staff.email
        assert emails[0].email_type == EmailType.ACTIVATION
        assert emails[0].triggered_by == system_admin.id

    async def test_student_activation_email_queued(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        registered_student: UserCredentials,
    ) -> None:
        emails = await EmailRepository.get_by_triggered_by(
            test_session, system_admin.id
        )

        assert len(emails) == 1
        assert emails[0].recipient_email == registered_student.email
        assert emails[0].email_type == EmailType.ACTIVATION
        assert emails[0].triggered_by == system_admin.id

    async def test_new_guardian_activation_email_queued(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        registered_new_guardian: UserCredentials,
    ) -> None:
        emails = await EmailRepository.get_by_triggered_by(
            test_session, system_admin.id
        )

        assert len(emails) == 1
        assert emails[0].recipient_email == registered_new_guardian.email
        assert emails[0].email_type == EmailType.ACTIVATION
        assert emails[0].triggered_by == system_admin.id


class TestSuccessShape:
    async def test_staff_response_shape(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
    ) -> None:
        response = await UserService.register_user(
            test_session, system_admin.id, valid_staff_payload
        )

        assert response["public_id"] is not None
        assert response["username"] == valid_staff_payload.username
        assert response["email"] == valid_staff_payload.email
        assert response["role"] == UserRole.TEACHER
        assert response["account_type"] == AccountType.WORK
        assert response["status"] == UserStatus.PENDING_ACTIVATION
        assert response["firstname"] == valid_staff_payload.firstname
        assert response["lastname"] == valid_staff_payload.lastname
        assert response["deletion_scheduled_for"] is None
        assert response["created_at"] is not None
        assert response["updated_at"] is not None

    async def test_student_response_shape(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        valid_student_payload: CreateStudent,
    ) -> None:
        response = await UserService.register_user(
            test_session, system_admin.id, valid_student_payload
        )

        assert response["public_id"] is not None
        assert response["username"] == valid_student_payload.username
        assert response["email"] == valid_student_payload.email
        assert response["role"] == UserRole.STUDENT
        assert response["account_type"] == AccountType.STUDENT
        assert response["status"] == UserStatus.PENDING_ACTIVATION
        assert response["firstname"] == valid_student_payload.firstname
        assert response["lastname"] == valid_student_payload.lastname
        assert response["deletion_scheduled_for"] is None
        assert response["created_at"] is not None
        assert response["updated_at"] is not None

    async def test_new_guardian_response_shape(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        valid_new_guardian_payload: CreateGuardianWithNewIdentity,
    ) -> None:
        response = await UserService.register_user(
            test_session, system_admin.id, valid_new_guardian_payload
        )

        assert response["public_id"] is not None
        assert response["username"] == valid_new_guardian_payload.username
        assert response["email"] == valid_new_guardian_payload.email
        assert response["role"] == UserRole.GUARDIAN
        assert response["account_type"] == AccountType.PERSONAL
        assert response["status"] == UserStatus.PENDING_ACTIVATION
        assert response["firstname"] == valid_new_guardian_payload.firstname
        assert response["lastname"] == valid_new_guardian_payload.lastname
        assert response["deletion_scheduled_for"] is None
        assert response["created_at"] is not None
        assert response["updated_at"] is not None

    async def test_existing_guardian_response_includes_identity_fields(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        existing_identity: UserCredentials,
        valid_existing_guardian_payload: CreateGuardianWithExistingIdentity,
    ) -> None:
        response = await UserService.register_user(
            test_session, system_admin.id, valid_existing_guardian_payload
        )

        user_identity = await UserIdentityRepository.get_by_id(
            test_session, existing_identity.identity_id
        )

        assert response["public_id"] is not None
        assert response["username"] == valid_existing_guardian_payload.username
        assert response["email"] == valid_existing_guardian_payload.email
        assert response["role"] == UserRole.GUARDIAN
        assert response["account_type"] == AccountType.PERSONAL
        assert response["status"] == UserStatus.PENDING_ACTIVATION
        assert response["firstname"] == user_identity.firstname
        assert response["lastname"] == user_identity.lastname
        assert response["phone_number"] == user_identity.phone_number
