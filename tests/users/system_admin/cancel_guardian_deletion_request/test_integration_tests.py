import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.utils.enums import UserStatus
from tests.conftest import make_auth_header
from tests.factories import make_guardian

ENDPOINT = "/api/v1/admin/users"


class TestAuth:
    async def test_unauthenticated_returns_401(self, integration_client: AsyncClient):
        response = await integration_client.post(
            f"{ENDPOINT}/{uuid.uuid4()}/cancel-deletion"
        )

        assert response.status_code == 401

    async def test_director_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        director: UserCredentials,
    ):
        headers = await make_auth_header(test_session, director)

        response = await integration_client.post(
            f"{ENDPOINT}/{uuid.uuid4()}/cancel-deletion",
            headers=headers,
        )

        assert response.status_code == 403

    async def test_teacher_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        headers = await make_auth_header(test_session, teacher)

        response = await integration_client.post(
            f"{ENDPOINT}/{uuid.uuid4()}/cancel-deletion",
            headers=headers,
        )

        assert response.status_code == 403

    async def test_student_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        student: UserCredentials,
    ):
        headers = await make_auth_header(test_session, student)

        response = await integration_client.post(
            f"{ENDPOINT}/{uuid.uuid4()}/cancel-deletion",
            headers=headers,
        )

        assert response.status_code == 403

    async def test_guardian_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        guardian: UserCredentials,
    ):
        headers = await make_auth_header(test_session, guardian)

        response = await integration_client.post(
            f"{ENDPOINT}/{uuid.uuid4()}/cancel-deletion",
            headers=headers,
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

        response = await integration_client.post(
            f"{ENDPOINT}/{uuid.uuid4()}/cancel-deletion",
            headers=headers,
        )

        assert response.status_code == 404


class TestStatusValidation:
    @pytest.mark.parametrize(
        "invalid_status",
        [
            UserStatus.ACTIVE,
            UserStatus.DEACTIVATED,
            UserStatus.PENDING_ACTIVATION,
        ],
    )
    async def test_non_pending_deletion_status_returns_409(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
        invalid_status: UserStatus,
    ):
        guardian = await make_guardian(test_session, status=invalid_status)
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.post(
            f"{ENDPOINT}/{guardian.public_id}/cancel-deletion",
            headers=headers,
        )

        assert response.status_code == 404


class TestSuccess:
    async def test_returns_204(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ):
        guardian = await make_guardian(test_session, status=UserStatus.PENDING_DELETION)
        guardian.pre_transition_status = UserStatus.ACTIVE
        await test_session.flush()

        headers = await make_auth_header(test_session, system_admin)

        with patch(
            "src.users.services.system_admin.emails.send_email_safe",
            new_callable=AsyncMock,
        ):
            response = await integration_client.post(
                f"{ENDPOINT}/{guardian.public_id}/cancel-deletion",
                headers=headers,
            )

        assert response.status_code == 204
