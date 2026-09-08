import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserIdentityRepository
from src.users.schemas.system_admin import (
    CreateGuardianWithExistingIdentity,
    CreateGuardianWithNewIdentity,
    CreateStaff,
    CreateStudent,
)
from src.users.utils.enums import AccountType, UserRole, UserStatus
from tests.conftest import make_auth_header
from tests.factories import make_student, make_teacher

ENDPOINT = "/api/v1/admin/users"


# HELPERS
def _assert_response_shape(data: dict) -> None:
    assert data["public_id"] is not None
    assert data["username"] is not None
    assert data["email"] is not None
    assert data["role"] is not None
    assert data["account_type"] is not None
    assert data["status"] is not None
    assert data["firstname"] is not None
    assert data["lastname"] is not None
    assert data["phone_number"] is not None
    assert data["created_at"] is not None
    assert data["updated_at"] is not None
    assert "deletion_scheduled_for" in data
    assert "middlename" in data
    assert "date_of_birth" in data
    assert "address" in data


class TestAuth:
    async def test_unauthenticated_returns_401(
        self, integration_client: AsyncClient
    ) -> None:
        response = await integration_client.post(ENDPOINT, json={})

        assert response.status_code == 401

    async def test_director_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        valid_staff_payload: CreateStaff,
        director: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, director)

        response = await integration_client.post(
            ENDPOINT,
            json=valid_staff_payload.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 403

    async def test_teacher_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        valid_staff_payload: CreateStaff,
        teacher: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, teacher)

        response = await integration_client.post(
            ENDPOINT,
            json=valid_staff_payload.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 403

    async def test_student_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        valid_staff_payload: CreateStaff,
        student: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, student)

        response = await integration_client.post(
            ENDPOINT,
            json=valid_staff_payload.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 403

    async def test_guardian_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        valid_staff_payload: CreateStaff,
        guardian: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, guardian)

        response = await integration_client.post(
            ENDPOINT,
            json=valid_staff_payload.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 403


class TestSuccessfulRegistration:
    async def test_register_staff_returns_201(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.post(
            ENDPOINT,
            json=valid_staff_payload.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 201

    async def test_register_staff_response_shape(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.post(
            ENDPOINT,
            json=valid_staff_payload.model_dump(mode="json"),
            headers=headers,
        )
        data = response.json()

        print(data)
        _assert_response_shape(data)
        assert data["role"] == UserRole.TEACHER.value
        assert data["account_type"] == AccountType.WORK.value
        assert data["status"] == UserStatus.PENDING_ACTIVATION.value
        assert data["username"] == valid_staff_payload.username
        assert data["email"] == valid_staff_payload.email

    async def test_register_student_returns_201(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
        valid_student_payload: CreateStudent,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.post(
            ENDPOINT,
            json=valid_student_payload.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 201

    async def test_register_student_response_shape(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
        valid_student_payload: CreateStudent,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.post(
            ENDPOINT,
            json=valid_student_payload.model_dump(mode="json"),
            headers=headers,
        )
        data = response.json()

        _assert_response_shape(data)
        assert data["role"] == UserRole.STUDENT.value
        assert data["account_type"] == AccountType.STUDENT.value
        assert data["status"] == UserStatus.PENDING_ACTIVATION.value
        assert data["date_of_birth"] == str(valid_student_payload.date_of_birth)

    async def test_register_new_guardian_returns_201(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
        valid_new_guardian_payload: CreateGuardianWithNewIdentity,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.post(
            ENDPOINT,
            json=valid_new_guardian_payload.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 201

    async def test_register_new_guardian_response_shape(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
        valid_new_guardian_payload: CreateGuardianWithNewIdentity,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.post(
            ENDPOINT,
            json=valid_new_guardian_payload.model_dump(mode="json"),
            headers=headers,
        )
        data = response.json()

        _assert_response_shape(data)
        assert data["role"] == UserRole.GUARDIAN.value
        assert data["account_type"] == AccountType.PERSONAL.value
        assert data["status"] == UserStatus.PENDING_ACTIVATION.value

    async def test_register_existing_guardian_returns_201(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ) -> None:
        staff = await make_teacher(test_session)
        payload = CreateGuardianWithExistingIdentity(
            type="existing_guardian",
            existing_identity_id=staff.identity_id,
            username="existing_g_user",
            email="existing.g@example.com",
        )
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.post(
            ENDPOINT,
            json=payload.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 201

    async def test_register_existing_guardian_response_includes_identity_fields(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ) -> None:
        staff = await make_teacher(test_session)
        payload = CreateGuardianWithExistingIdentity(
            type="existing_guardian",
            existing_identity_id=staff.identity_id,
            username="existing_g_user2",
            email="existing.g2@example.com",
        )
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.post(
            ENDPOINT,
            json=payload.model_dump(mode="json"),
            headers=headers,
        )
        data = response.json()

        user_identity = await UserIdentityRepository.get_by_id(
            test_session, staff.identity_id
        )

        _assert_response_shape(data)
        assert data["role"] == UserRole.GUARDIAN.value
        assert data["account_type"] == AccountType.PERSONAL.value
        assert data["firstname"] == user_identity.firstname
        assert data["lastname"] == user_identity.lastname
        assert data["phone_number"] == user_identity.phone_number


class TestDuplicateFieldRejection:
    @pytest.mark.parametrize(
        ("existing_kwargs", "override"),
        [
            ({"username": "taken_username"}, {"username": "taken_username"}),
            ({"phone_number": "+992333333333"}, {"phone_number": "+992333333333"}),
            (
                {"email": "taken.staff@meridian.edu"},
                {"email": "taken.staff@meridian.edu"},
            ),
        ],
    )
    async def test_staff_duplicate_fields_return_409(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
        existing_kwargs: dict,
        override: dict,
    ) -> None:
        await make_teacher(test_session, **existing_kwargs)

        for field, value in override.items():
            setattr(valid_staff_payload, field, value)

        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.post(
            ENDPOINT,
            json=valid_staff_payload.model_dump(mode="json"),
            headers=headers,
        )
        print(response.json())
        assert response.status_code == 409

    @pytest.mark.parametrize(
        ("existing_kwargs", "override"),
        [
            ({"username": "taken_username"}, {"username": "taken_username"}),
            ({"phone_number": "+992555111333"}, {"phone_number": "+992555111333"}),
            (
                {"email": "taken.student@example.com"},
                {"email": "taken.student@example.com"},
            ),
        ],
    )
    async def test_student_duplicate_fields_return_409(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
        valid_student_payload: CreateStudent,
        existing_kwargs: dict,
        override: dict,
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

        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.post(
            ENDPOINT,
            json=valid_student_payload.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 409

    async def test_existing_guardian_with_unknown_identity_returns_404(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ) -> None:
        payload = CreateGuardianWithExistingIdentity(
            type="existing_guardian",
            existing_identity_id=999999,
            username="ghost_guardian",
            email="ghost@example.com",
        )
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.post(
            ENDPOINT,
            json=payload.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 404

    async def test_existing_guardian_duplicate_returns_409(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ) -> None:
        staff = await make_teacher(test_session)
        headers = await make_auth_header(test_session, system_admin)

        first_payload = CreateGuardianWithExistingIdentity(
            type="existing_guardian",
            existing_identity_id=staff.identity_id,
            username="first_guardian",
            email="first.guardian@example.com",
        )
        await integration_client.post(
            ENDPOINT,
            json=first_payload.model_dump(mode="json"),
            headers=headers,
        )

        second_payload = CreateGuardianWithExistingIdentity(
            type="existing_guardian",
            existing_identity_id=staff.identity_id,
            username="second_guardian",
            email="second.guardian@example.com",
        )
        response = await integration_client.post(
            ENDPOINT,
            json=second_payload.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 409


class TestValidation:
    @pytest.mark.parametrize(
        ("field", "invalid_value"),
        [
            ("username", "bad!name"),
            ("username", "ab"),
            ("email", "not-an-email"),
            ("firstname", "A"),
            ("phone_number", "not-a-phone"),
        ],
    )
    async def test_invalid_fields_return_422(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
        field: str,
        invalid_value: str,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)
        payload = valid_staff_payload.model_dump(mode="json")
        payload[field] = invalid_value

        response = await integration_client.post(
            ENDPOINT, json=payload, headers=headers
        )

        assert response.status_code == 422

    async def test_student_missing_date_of_birth_returns_422(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
        valid_student_payload: CreateStudent,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)
        payload = valid_student_payload.model_dump(mode="json")
        del payload["date_of_birth"]

        response = await integration_client.post(
            ENDPOINT, json=payload, headers=headers
        )

        assert response.status_code == 422

    async def test_staff_non_work_email_domain_returns_422(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)
        payload = valid_staff_payload.model_dump(mode="json")
        payload["email"] = "personal@gmail.com"

        response = await integration_client.post(
            ENDPOINT, json=payload, headers=headers
        )

        assert response.status_code == 422

    async def test_missing_type_discriminator_returns_422(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
        valid_staff_payload: CreateStaff,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)
        payload = valid_staff_payload.model_dump(mode="json")
        del payload["type"]

        response = await integration_client.post(
            ENDPOINT, json=payload, headers=headers
        )

        assert response.status_code == 422

    async def test_empty_body_returns_422(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.post(ENDPOINT, json={}, headers=headers)

        assert response.status_code == 422
