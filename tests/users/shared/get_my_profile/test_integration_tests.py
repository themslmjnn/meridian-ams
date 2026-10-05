import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from tests.conftest import make_auth_header
from tests.factories import make_student

ENDPOINT = "/api/v1/users/me"


class TestAuth:
    async def test_unauthenticated_returns_401(self, integration_client: AsyncClient):
        response = await integration_client.get(ENDPOINT)

        assert response.status_code == 401

    async def test_student_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        student: UserCredentials,
    ):
        headers = await make_auth_header(test_session, student)

        response = await integration_client.get(ENDPOINT, headers=headers)

        assert response.status_code == 404


class TestNotFound:
    async def test_student_public_id_returns_404(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ):
        student = await make_student(test_session)
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.get(
            f"{ENDPOINT}/{student.public_id}", headers=headers
        )

        assert response.status_code == 404


class TestSuccess:
    async def test_returns_200(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ):
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.get(ENDPOINT, headers=headers)

        assert response.status_code == 200

    async def test_response_shape(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ):
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.get(ENDPOINT, headers=headers)
        data = response.json()

        assert data["public_id"] == str(system_admin.public_id)
        assert data["username"] == system_admin.username
        assert data["email"] == system_admin.email
        assert "firstname" in data
        assert "lastname" in data
        assert "created_at" in data
