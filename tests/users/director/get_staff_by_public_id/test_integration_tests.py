import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.utils.enums import UserRole, UserStatus
from tests.conftest import make_auth_header
from tests.factories import make_student, make_teacher

ENDPOINT = "/api/v1/director/users/staff"


class TestAuth:
    async def test_unauthenticated_returns_401(self, integration_client: AsyncClient):
        response = await integration_client.get(f"{ENDPOINT}/{uuid.uuid4()}")

        assert response.status_code == 401

    async def test_system_admin_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ):
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.get(
            f"{ENDPOINT}/{uuid.uuid4()}", headers=headers
        )

        assert response.status_code == 403

    async def test_teacher_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        headers = await make_auth_header(test_session, teacher)

        response = await integration_client.get(
            f"{ENDPOINT}/{uuid.uuid4()}", headers=headers
        )

        assert response.status_code == 403

    async def test_student_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        student: UserCredentials,
    ):
        headers = await make_auth_header(test_session, student)

        response = await integration_client.get(
            f"{ENDPOINT}/{uuid.uuid4()}", headers=headers
        )

        assert response.status_code == 403

    async def test_guardian_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        guardian: UserCredentials,
    ):
        headers = await make_auth_header(test_session, guardian)

        response = await integration_client.get(
            f"{ENDPOINT}/{uuid.uuid4()}", headers=headers
        )

        assert response.status_code == 403


class TestNotFound:
    async def test_unknown_public_id_returns_404(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        director: UserCredentials,
    ):
        headers = await make_auth_header(test_session, director)

        response = await integration_client.get(
            f"{ENDPOINT}/{uuid.uuid4()}", headers=headers
        )

        assert response.status_code == 404

    async def test_student_public_id_returns_404(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        director: UserCredentials,
    ):
        student = await make_student(test_session)
        headers = await make_auth_header(test_session, director)

        response = await integration_client.get(
            f"{ENDPOINT}/{student.public_id}", headers=headers
        )

        assert response.status_code == 404


class TestSuccess:
    async def test_returns_200(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        director: UserCredentials,
    ):
        teacher = await make_teacher(test_session)
        headers = await make_auth_header(test_session, director)

        response = await integration_client.get(
            f"{ENDPOINT}/{teacher.public_id}", headers=headers
        )

        assert response.status_code == 200

    async def test_response_shape(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        director: UserCredentials,
    ):
        teacher = await make_teacher(test_session)
        headers = await make_auth_header(test_session, director)

        response = await integration_client.get(
            f"{ENDPOINT}/{teacher.public_id}", headers=headers
        )
        data = response.json()

        assert data["username"] == teacher.username
        assert data["email"] == teacher.email
        assert data["role"] == UserRole.TEACHER.value
        assert data["status"] == UserStatus.ACTIVE.value
        assert "firstname" in data
        assert "lastname" in data
        assert "date_of_birth" in data
        assert "address" in data
        assert "created_at" in data
