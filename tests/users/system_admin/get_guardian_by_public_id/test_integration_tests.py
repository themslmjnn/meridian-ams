import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.utils.enums import AccountType, UserRole, UserStatus
from tests.conftest import make_auth_header
from tests.factories import make_guardian, make_teacher

ENDPOINT = "/api/v1/admin/users/guardians"


class TestAuth:
        async def test_unauthenticated_returns_401(
            self, integration_client: AsyncClient
        ):
            response = await integration_client.get(f"{ENDPOINT}/{uuid.uuid4()}")

            assert response.status_code == 401

        async def test_director_returns_403(
            self,
            test_session: AsyncSession,
            integration_client: AsyncClient,
            director: UserCredentials,
        ):
            headers = await make_auth_header(test_session, director)

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
            system_admin: UserCredentials,
        ):
            headers = await make_auth_header(test_session, system_admin)

            response = await integration_client.get(
                f"{ENDPOINT}/{uuid.uuid4()}", headers=headers
            )

            assert response.status_code == 404

        async def test_teacher_public_id_returns_404(
            self,
            test_session: AsyncSession,
            integration_client: AsyncClient,
            system_admin: UserCredentials,
        ):
            teacher = await make_teacher(test_session)
            headers = await make_auth_header(test_session, system_admin)

            response = await integration_client.get(
                f"{ENDPOINT}/{teacher.public_id}", headers=headers
            )

            assert response.status_code == 404

class TestSuccess:
        async def test_returns_200(
            self,
            test_session: AsyncSession,
            integration_client: AsyncClient,
            system_admin: UserCredentials,
        ):
            guardian = await make_guardian(test_session)
            headers = await make_auth_header(test_session, system_admin)

            response = await integration_client.get(
                f"{ENDPOINT}/{guardian.public_id}", headers=headers
            )

            assert response.status_code == 200

        async def test_response_shape(
            self,
            test_session: AsyncSession,
            integration_client: AsyncClient,
            system_admin: UserCredentials,
        ):
            guardian = await make_guardian(test_session)
            headers = await make_auth_header(test_session, system_admin)

            response = await integration_client.get(
                f"{ENDPOINT}/{guardian.public_id}", headers=headers
            )
            data = response.json()

            assert data["public_id"] == str(guardian.public_id)
            assert data["username"] == guardian.username
            assert data["email"] == guardian.email
            assert data["role"] == UserRole.GUARDIAN.value
            assert data["account_type"] == AccountType.PERSONAL.value
            assert data["status"] == UserStatus.ACTIVE.value
            assert "firstname" in data
            assert "lastname" in data
            assert "date_of_birth" in data
            assert "address" in data
            assert "deletion_scheduled_for" in data
            assert "created_at" in data
            assert "updated_at" in data