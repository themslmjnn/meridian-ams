from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from tests.conftest import make_auth_header
from tests.factories import make_guardian

DELETION_ENDPOINT = "/api/v1/users/me/deletion"


@pytest.fixture
def mock_guardian_delete_cache(mocker):
    return mocker.patch("src.users.services.guardian.delete_cache")


@pytest.fixture
def mock_guardian_send_deletion_email(mocker):
    return mocker.patch(
        "src.users.services.guardian.emails.send_account_deletion_email"
    )


class TestCreateGuardianSelfDeletionRequestIntegration:
    async def test_unauthenticated_returns_401(self, integration_client: AsyncClient):
        response = await integration_client.post(DELETION_ENDPOINT)
        assert response.status_code == 401

    async def test_non_guardian_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        headers = await make_auth_header(test_session, teacher)
        response = await integration_client.post(DELETION_ENDPOINT, headers=headers)
        assert response.status_code == 403

    async def test_active_guardian_returns_204(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        mock_guardian_delete_cache,
        mock_guardian_send_deletion_email,
    ):
        user = await make_guardian(test_session)
        headers = await make_auth_header(test_session, user)
        response = await integration_client.post(DELETION_ENDPOINT, headers=headers)
        assert response.status_code == 204

    # async def test_already_pending_deletion_returns_409(
    #     self,
    #     test_session: AsyncSession,
    #     integration_client: AsyncClient,
    # ):
    #     user = await make_guardian(test_session, status=UserStatus.PENDING_DELETION)
    #     headers = await make_auth_header(test_session, user)
    #     response = await integration_client.post(DELETION_ENDPOINT, headers=headers)

    #     assert response.status_code == 409

    # async def test_inactive_guardian_returns_422(
    #     self,
    #     test_session: AsyncSession,
    #     integration_client: AsyncClient,
    # ):
    #     user = await make_guardian(test_session, status=UserStatus.DEACTIVATED)
    #     headers = await make_auth_header(test_session, user)
    #     response = await integration_client.post(DELETION_ENDPOINT, headers=headers)
    #     assert response.status_code == 422
