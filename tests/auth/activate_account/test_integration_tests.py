from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.utils.enums import UserStatus
from src.users.utils.exceptions import UserNotPendingActivationError
from src.utils import exceptions
from tests.auth.conftest import cookie_values, get_activation
from tests.auth.constants import NEW_PASSWORD, RAW_ACTIVATION_TOKEN
from tests.endpoints import AuthEndpoints, UserEndpoints


def payload_json(token=RAW_ACTIVATION_TOKEN, password=NEW_PASSWORD, confirm=None):
    return {
        "activation_token": token,
        "new_password": password,
        "confirm_password": confirm if confirm is not None else password,
    }


async def _activate(client: AsyncClient, **kwargs):
    return await client.post(AuthEndpoints.ACTIVATION, json=payload_json(**kwargs))


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _cookie_header(cookies):
    return {
        "Cookie": (
            f"refresh_token={cookies['refresh_token']}; "
            f"refresh_token_family={cookies['refresh_token_family']}"
        )
    }


class TestSuccessfulActivation:
    async def test_returns_200_and_token(
        self, integration_client: AsyncClient, pending_user: UserCredentials
    ):
        response = await _activate(integration_client)

        data = response.json()

        assert response.status_code == 200
        assert set(data) == {"access_token", "token_type"}
        assert data["token_type"] == "bearer"
        assert data["access_token"]

    async def test_sets_httponly_cookies_and_keeps_refresh_token_out_of_body(
        self, integration_client: AsyncClient, pending_user: UserCredentials
    ):
        response = await _activate(integration_client)

        headers = response.headers.get_list("set-cookie")
        cookies = cookie_values(headers)

        assert set(cookies) == {"refresh_token", "refresh_token_family", "device_id"}
        assert all("httponly" in h.lower() for h in headers)
        assert cookies["refresh_token"] not in response.text

    async def test_access_token_authenticates_protected_endpoint(
        self, integration_client: AsyncClient, pending_user: UserCredentials
    ):
        activated = await _activate(integration_client)

        response = await integration_client.get(
            UserEndpoints.ME, headers=_bearer(activated.json()["access_token"])
        )

        assert response.status_code == 200

    async def test_cookies_can_refresh(
        self, integration_client: AsyncClient, pending_user: UserCredentials
    ):
        activated = await _activate(integration_client)
        cookies = cookie_values(activated.headers.get_list("set-cookie"))
        integration_client.cookies.clear()

        response = await integration_client.post(
            AuthEndpoints.REFRESH, headers=_cookie_header(cookies)
        )

        assert response.status_code == 200

    async def test_new_password_works_on_login(
        self, integration_client: AsyncClient, pending_user: UserCredentials
    ):
        await _activate(integration_client)
        integration_client.cookies.clear()

        response = await integration_client.post(
            AuthEndpoints.LOGIN,
            data={"username": pending_user.username, "password": NEW_PASSWORD},
        )

        assert response.status_code == 200


class TestRejectedActivation:
    async def test_unknown_token(
        self, integration_client: AsyncClient, pending_user: UserCredentials
    ):
        expected = exceptions.InvalidActivationTokenError()

        response = await _activate(integration_client, token="no-such-token")

        assert response.status_code == expected.status_code
        assert response.json()["error_code"] == expected.error_code
        assert not response.headers.get_list("set-cookie")

    async def test_expired_token(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        pending_user: UserCredentials,
    ):
        activation = await get_activation(test_session, pending_user.id)
        activation.activation_token_expires_at = datetime.now(UTC) - timedelta(
            minutes=1
        )
        await test_session.flush()
        expected = exceptions.ExpiredActivationTokenError()

        response = await _activate(integration_client)

        assert response.status_code == expected.status_code
        assert response.json()["error_code"] == expected.error_code

    async def test_non_pending_status(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        pending_user: UserCredentials,
    ):
        pending_user.status = UserStatus.ACTIVE
        await test_session.flush()
        expected = UserNotPendingActivationError()

        response = await _activate(integration_client)

        assert response.status_code == expected.status_code
        assert response.json()["error_code"] == expected.error_code

    async def test_reused_token(
        self, integration_client: AsyncClient, pending_user: UserCredentials
    ):
        expected = exceptions.InvalidActivationTokenError()

        first = await _activate(integration_client)
        second = await _activate(integration_client)

        assert first.status_code == 200
        assert second.status_code == expected.status_code
        assert second.json()["error_code"] == expected.error_code


class TestValidation:
    async def test_mismatched_passwords_return_422(
        self, integration_client: AsyncClient, pending_user: UserCredentials
    ):
        response = await _activate(integration_client, confirm="Different!Passw0rd#1")

        assert response.status_code == 422

    async def test_weak_password_returns_422(
        self, integration_client: AsyncClient, pending_user: UserCredentials
    ):
        response = await _activate(integration_client, password="short")

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "missing", ["activation_token", "new_password", "confirm_password"]
    )
    async def test_missing_field_returns_422(
        self, integration_client: AsyncClient, pending_user: UserCredentials, missing
    ):
        body = payload_json()
        del body[missing]

        response = await integration_client.post(AuthEndpoints.ACTIVATION, json=body)

        assert response.status_code == 422


class TestRateLimit:
    async def test_fourth_request_within_a_minute_returns_429(
        self, integration_client: AsyncClient
    ):
        expected = exceptions.InvalidActivationTokenError().status_code

        statuses = [
            (await _activate(integration_client, token="no-such-token")).status_code
            for _ in range(4)
        ]

        assert statuses[:3] == [expected] * 3
        assert statuses[3] == 429
