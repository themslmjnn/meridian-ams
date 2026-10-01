import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.utils.enums import UserStatus
from tests.conftest import make_auth_header
from tests.factories import make_teacher

ENDPOINT = "/api/v1/admin/users"


def _make_headers(auth: dict) -> dict:
    return {**auth, "Idempotency-Key": str(uuid.uuid4())}


class TestSuccessfulCreation:
    async def test_returns_204_on_success(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ):
        headers = _make_headers(await make_auth_header(test_session, system_admin))

        response = await integration_client.post(
            f"{ENDPOINT}/{teacher.public_id}/password",
            headers=headers,
        )

        assert response.status_code == 204


class TestAuth:
    async def test_unauthenticated_returns_401(
        self,
        integration_client,
        teacher: UserCredentials,
    ):
        response = await integration_client.post(
            f"{ENDPOINT}/{teacher.public_id}/password"
        )

        assert response.status_code == 401

    async def test_director_returns_403(
        self,
        test_session: AsyncSession,
        integration_client,
        teacher: UserCredentials,
        director: UserCredentials,
    ):
        headers = _make_headers(await make_auth_header(test_session, director))

        response = await integration_client.post(
            f"{ENDPOINT}/{teacher.public_id}/password",
            headers=headers,
        )

        assert response.status_code == 403

    async def test_teacher_returns_403(
        self,
        test_session: AsyncSession,
        integration_client,
        teacher: UserCredentials,
    ):
        headers = _make_headers(await make_auth_header(test_session, teacher))

        response = await integration_client.post(
            f"{ENDPOINT}/{teacher.public_id}/password",
            headers=headers,
        )

        assert response.status_code == 403

    async def test_student_returns_403(
        self,
        test_session: AsyncSession,
        integration_client,
        teacher: UserCredentials,
        student: UserCredentials,
    ):
        headers = _make_headers(await make_auth_header(test_session, student))

        response = await integration_client.post(
            f"{ENDPOINT}/{teacher.public_id}/password",
            headers=headers,
        )

        assert response.status_code == 403

    async def test_guardian_returns_403(
        self,
        test_session: AsyncSession,
        integration_client,
        teacher: UserCredentials,
        guardian: UserCredentials,
    ):
        headers = _make_headers(await make_auth_header(test_session, guardian))

        response = await integration_client.post(
            f"{ENDPOINT}/{teacher.public_id}/password",
            headers=headers,
        )

        assert response.status_code == 403

    async def test_unknown_public_id_returns_404(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
    ):
        headers = _make_headers(await make_auth_header(test_session, system_admin))

        response = await integration_client.post(
            f"{ENDPOINT}/{uuid.uuid4()}/password",
            headers=headers,
        )

        assert response.status_code == 404


class TestStatusTransition:
    async def test_invalid_status_transition_returns_403(
        self,
        test_session: AsyncSession,
        integration_client,
        system_admin: UserCredentials,
    ):
        deactivated = await make_teacher(test_session, status=UserStatus.DEACTIVATED)
        headers = _make_headers(await make_auth_header(test_session, system_admin))

        response = await integration_client.post(
            f"{ENDPOINT}/{deactivated.public_id}/password",
            headers=headers,
        )

        assert response.status_code == 403
