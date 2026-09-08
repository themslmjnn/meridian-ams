import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.utils.schemas import UpdateCredentials
from tests.conftest import make_auth_header
from tests.factories import make_teacher

ENDPOINT = "/api/v1/admin/users"


class TestSuccessUpdate:
    async def test_username_update_returns_204(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)
        payload = UpdateCredentials(username="integration1").model_dump(
            mode="json", exclude_unset=True
        )

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/credentials",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 204

    async def test_email_update_returns_204(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)
        payload = UpdateCredentials(email="integration.new@school.com").model_dump(
            mode="json", exclude_unset=True
        )

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/credentials",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 204


class TestAuth:
    async def test_unauthenticated_returns_401(
        self,
        integration_client,
        teacher: UserCredentials,
    ) -> None:
        payload = UpdateCredentials(username="integration2").model_dump(
            mode="json", exclude_unset=True
        )

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/credentials",
            json=payload,
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
        payload = UpdateCredentials(username="integration3").model_dump(
            mode="json", exclude_unset=True
        )

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/credentials",
            json=payload,
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
        payload = UpdateCredentials(username="integration3").model_dump(
            mode="json", exclude_unset=True
        )

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/credentials",
            json=payload,
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
        payload = UpdateCredentials(username="integration3").model_dump(
            mode="json", exclude_unset=True
        )

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/credentials",
            json=payload,
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
        payload = UpdateCredentials(username="integration3").model_dump(
            mode="json", exclude_unset=True
        )

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/credentials",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 403

    async def test_unknown_public_id_returns_404(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)
        payload = UpdateCredentials(username="integration4").model_dump(
            mode="json", exclude_unset=True
        )

        response = await integration_client.patch(
            f"{ENDPOINT}/{uuid.uuid4()}/credentials",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 404


class TestDuplicateRejection:
    async def test_duplicate_username_returns_409(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ) -> None:
        existing = await make_teacher(test_session, username="takenusername2")
        headers = await make_auth_header(test_session, system_admin)
        payload = UpdateCredentials(username=existing.username).model_dump(
            mode="json", exclude_unset=True
        )

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/credentials",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 409

    async def test_duplicate_email_returns_409(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ) -> None:
        existing = await make_teacher(test_session)
        headers = await make_auth_header(test_session, system_admin)
        payload = UpdateCredentials(email=existing.email).model_dump(
            mode="json", exclude_unset=True
        )

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/credentials",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 409


class TestValidation:
    async def test_no_fields_provided_returns_422(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ) -> None:
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/credentials",
            json={},
            headers=headers,
        )

        assert response.status_code == 422

    @pytest.mark.parametrize(
        ("field", "invalid_value"),
        [
            ("username", "bad!"),
            ("username", "ab"),
            ("email", "not-an-email"),
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
        payload = {field: invalid_value}

        response = await integration_client.patch(
            f"{ENDPOINT}/{teacher.public_id}/credentials",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 422
