import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from tests.conftest import make_auth_header
from tests.factories import make_guardian

PROFILE_ENDPOINT = "/api/v1/users/me/profile"


@pytest.fixture
def mock_guardian_advisory_lock(mocker):
    return mocker.patch("src.users.services.guardian.acquire_contact_locks")


@pytest.fixture
def mock_guardian_check_contact_limit(mocker):
    return mocker.patch("src.users.services.guardian.check_contact_limit")


@pytest.fixture
def mock_guardian_delete_cache(mocker):
    return mocker.patch("src.users.services.guardian.delete_cache")


@pytest.fixture
def mock_guardian_send_deletion_email(mocker):
    return mocker.patch(
        "src.users.services.guardian.emails.send_account_deletion_email"
    )


class TestUpdateMeProfileIntegration:
    async def test_unauthenticated_returns_401(self, integration_client):
        response = await integration_client.patch(PROFILE_ENDPOINT, json={})
        assert response.status_code == 401

    async def test_non_guardian_returns_403(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        headers = await make_auth_header(test_session, teacher)
        response = await integration_client.patch(
            PROFILE_ENDPOINT, json={"firstname": "New"}, headers=headers
        )
        assert response.status_code == 403

    async def test_valid_update_returns_204(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        mock_guardian_advisory_lock,
        mock_guardian_check_contact_limit,
        mock_guardian_delete_cache,
        mock_send_account_info_updated_email,
    ):
        user = await make_guardian(test_session)
        headers = await make_auth_header(test_session, user)
        response = await integration_client.patch(
            PROFILE_ENDPOINT,
            json={"firstname": "Updated"},
            headers=headers,
        )
        assert response.status_code == 204

    async def test_duplicate_phone_returns_409(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        mock_guardian_delete_cache,
        mock_send_account_info_updated_email,
    ):
        await make_guardian(test_session, phone_number="+992555000020")
        user = await make_guardian(test_session)
        headers = await make_auth_header(test_session, user)
        response = await integration_client.patch(
            PROFILE_ENDPOINT,
            json={"phone_number": "+992555000020"},
            headers=headers,
        )
        assert response.status_code == 409

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
        integration_client: AsyncClient,
        field: str,
        invalid_value: str,
    ):
        user = await make_guardian(test_session)
        headers = await make_auth_header(test_session, user)
        response = await integration_client.patch(
            PROFILE_ENDPOINT,
            json={field: invalid_value},
            headers=headers,
        )
        assert response.status_code == 422

    async def test_empty_body_returns_400(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        mock_guardian_advisory_lock,
        mock_guardian_check_contact_limit,
        mock_guardian_delete_cache,
        mock_send_account_info_updated_email,
    ):
        # All fields optional — empty payload is a valid no-op
        user = await make_guardian(test_session)
        headers = await make_auth_header(test_session, user)
        response = await integration_client.patch(
            PROFILE_ENDPOINT, json={}, headers=headers
        )
        assert response.status_code == 400
