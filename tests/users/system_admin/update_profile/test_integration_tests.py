import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserIdentityRepository
from src.users.schemas.system_admin import (
    UpdateStaffOrGuardianProfile,
    UpdateStudentProfile,
)
from tests.conftest import make_auth_header
from tests.factories import make_teacher

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

ENDPOINT = "/api/v1/admin/users"


class TestSuccessUpdate:
    async def test_staff_update_returns_204(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)
        payload = UpdateStaffOrGuardianProfile(
            type="staff_or_guardian",
            firstname="UpdatedFirst",
        )

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/profile",
            json=payload.model_dump(mode="json", exclude_unset=True),
            headers=headers,
        )

        assert response.status_code == 204

    async def test_student_update_returns_204(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
        student: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)
        payload = UpdateStudentProfile(
            type="student",
            firstname="UpdatedFirst",
        )

        response = await integration_client.patch(
            f"{ENDPOINT}/{student.public_id}/profile",
            json=payload.model_dump(mode="json", exclude_unset=True),
            headers=headers,
        )

        assert response.status_code == 204


class TestNotFound:
    async def test_unknown_public_id_returns_404(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)
        payload = STAFF_GUARDIAN_UPDATE.model_dump(mode="json")

        response = await integration_client.patch(
            f"{ENDPOINT}/{uuid.uuid4()}/profile",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 404


class TestPayloadMismatch:
    async def test_payload_mismatch_returns_400(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)
        payload = UpdateStudentProfile(type="student", firstname="Updated")

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/profile",
            json=payload.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 400


class TestAuth:
    async def test_unauthenticated_returns_401(
        self,
        integration_client,
        teacher: UserCredentials,
    ) -> None:
        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/profile",
            json=STAFF_GUARDIAN_UPDATE.model_dump(mode="json"),
        )

        assert response.status_code == 401

    async def test_director_returns_403(
        self,
        test_session: AsyncSession,
        integration_client,
        teacher: UserCredentials,
        director: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, director)

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/profile",
            json=STAFF_GUARDIAN_UPDATE.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 403

    async def test_teacher_returns_403(
        self,
        test_session: AsyncSession,
        integration_client,
        teacher: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, teacher)

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/profile",
            json=STAFF_GUARDIAN_UPDATE.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 403

    async def test_student_returns_403(
        self,
        test_session: AsyncSession,
        integration_client,
        teacher: UserCredentials,
        student: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, student)

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/profile",
            json=STAFF_GUARDIAN_UPDATE.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 403

    async def test_guardian_returns_403(
        self,
        test_session: AsyncSession,
        integration_client,
        teacher: UserCredentials,
        guardian: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, guardian)

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/profile",
            json=STAFF_GUARDIAN_UPDATE.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 403

    async def test_duplicate_phone_returns_409(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ) -> None:
        existing = await make_teacher(test_session, phone_number="+992555111888")
        user_identity = await UserIdentityRepository.get_by_id(
            test_session, existing.identity_id
        )
        headers = await make_auth_header(test_session, system_admin)
        payload = UpdateStaffOrGuardianProfile(
            type="staff_or_guardian",
            phone_number=user_identity.phone_number,
        )

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/profile",
            json=payload.model_dump(mode="json"),
            headers=headers,
        )

        assert response.status_code == 409


class TestValidation:
    @pytest.mark.parametrize(
        ("field", "invalid_value"),
        [
            ("firstname", "A"),
            ("lastname", "B"),
            ("phone_number", "not-a-phone"),
        ],
    )
    async def test_invalid_fields_return_422(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
        teacher: UserCredentials,
        field: str,
        invalid_value: str,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)
        payload = STAFF_GUARDIAN_UPDATE.model_dump(mode="json")
        payload[field] = invalid_value

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/profile",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 422
