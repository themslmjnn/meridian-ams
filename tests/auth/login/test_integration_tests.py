from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.repository import AuthRepository
from src.users.utils.enums import UserStatus
from src.utils import exceptions
from tests.auth.conftest import (
    PASSWORD,
    get_history,
    get_lockout,
    prepare_for_login,
)

ENDPOINT = "/api/v1/auth/login"


async def _login(client: AsyncClient, username: str, password: str = PASSWORD):
    return await client.post(
        ENDPOINT,
        data={"username": username, "password": password},
    )


class TestSuccessfulLogin:
    async def test_returns_200_and_token(
        self, integration_client: AsyncClient, login_user
    ):
        response = await _login(integration_client, login_user.username)

        data = response.json()

        assert response.status_code == 200
        assert set(data) == {"access_token", "token_type"}
        assert data["token_type"] == "bearer"
        assert data["access_token"]

    async def test_sets_httponly_cookies_and_keeps_refresh_token_out_of_body(
        self, integration_client: AsyncClient, login_user
    ):
        response = await _login(integration_client, login_user.username)

        headers = response.headers.get_list("set-cookie")
        names = {h.split("=", 1)[0] for h in headers}

        assert names == {"refresh_token", "refresh_token_family", "device_id"}
        assert all("httponly" in h.lower() for h in headers)
        assert response.cookies["refresh_token"] not in response.text

    async def test_access_token_authenticates_protected_endpoint(
        self, integration_client: AsyncClient, login_user
    ):
        login = await _login(integration_client, login_user.username)
        token = login.json()["access_token"]

        response = await integration_client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

    async def test_writes_history_row(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        login_user,
    ):
        await _login(integration_client, login_user.username)

        history = await get_history(test_session, login_user.id)

        assert len(history) == 1
        assert history[0].success is True
        assert history[0].ip_address is not None

    async def test_second_login_with_device_cookie_reuses_session(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        login_user,
    ):
        first = await _login(integration_client, login_user.username)
        device_id = first.cookies["device_id"]
        count_after_first = await AuthRepository.get_session_count(
            test_session, login_user.id
        )

        integration_client.cookies.clear()
        integration_client.cookies.set("device_id", device_id)

        second = await _login(integration_client, login_user.username)

        count_after_second = await AuthRepository.get_session_count(
            test_session, login_user.id
        )

        assert second.status_code == 200
        assert count_after_second == count_after_first
        assert second.cookies["device_id"] == device_id


class TestFailedLogin:
    async def test_wrong_password_returns_401(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        login_user,
    ):
        response = await _login(integration_client, login_user.username, "wrong")

        lockout = await get_lockout(test_session, login_user.id)

        assert response.status_code == exceptions.InvalidCredentialsError().status_code
        assert response.status_code == 401
        assert lockout.failed_attempts == 1
        assert not response.headers.get_list("set-cookie")

    async def test_unknown_user_matches_wrong_password_response(
        self, integration_client: AsyncClient, login_user
    ):
        wrong_password = await _login(integration_client, login_user.username, "wrong")
        unknown_user = await _login(integration_client, "no_such_user", "wrong")

        assert unknown_user.status_code == 401
        assert unknown_user.json() == wrong_password.json()

    async def test_locked_account_returns_lockout_error(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        login_user,
    ):
        lockout = await get_lockout(test_session, login_user.id)
        lockout.locked_until = datetime.now(UTC) + timedelta(minutes=10)

        await test_session.flush()

        expected = exceptions.AccountLockedError()

        response = await _login(integration_client, login_user.username)

        assert response.status_code == expected.status_code
        assert response.json()["error_code"] == expected.error_code

    async def test_pending_activation_rejected(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        login_user,
    ):
        await prepare_for_login(test_session, login_user, UserStatus.PENDING_ACTIVATION)
        expected = exceptions.AccountInactiveError()

        response = await _login(integration_client, login_user.username)

        assert response.status_code == expected.status_code
        assert response.json()["error_code"] == expected.error_code

    @pytest.mark.parametrize(
        "status",
        [
            UserStatus.DEACTIVATED,
            UserStatus.GRADUATED,
            UserStatus.EXPELLED,
            UserStatus.WITHDRAWN,
        ],
    )
    async def test_non_loginable_status_rejected(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        login_user,
        status,
    ):
        await prepare_for_login(test_session, login_user, status)
        expected = exceptions.AccessDeniedError()

        response = await _login(integration_client, login_user.username)

        assert response.status_code == expected.status_code
        assert response.json()["error_code"] == expected.error_code

    async def test_expired_deletion_grace_returns_401(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        login_user,
    ):
        login_user.status = UserStatus.PENDING_DELETION
        login_user.pre_transition_status = UserStatus.ACTIVE
        login_user.deletion_scheduled_for = datetime.now(UTC) - timedelta(minutes=1)

        await test_session.flush()

        response = await _login(integration_client, login_user.username)

        assert response.status_code == 401


class TestValidation:
    @pytest.mark.parametrize("missing", ["username", "password"])
    async def test_missing_form_field_returns_422(
        self, integration_client: AsyncClient, login_user, missing
    ):
        data = {"username": login_user.username, "password": PASSWORD}
        del data[missing]

        response = await integration_client.post(ENDPOINT, data=data)

        assert response.status_code == 422

    async def test_json_body_returns_422(
        self, integration_client: AsyncClient, login_user
    ):
        response = await integration_client.post(
            ENDPOINT,
            json={"username": login_user.username, "password": PASSWORD},
        )

        assert response.status_code == 422


class TestRateLimit:
    async def test_sixth_request_within_a_minute_returns_429(
        self, integration_client: AsyncClient
    ):
        statuses = [
            (await _login(integration_client, "no_such_user")).status_code
            for _ in range(6)
        ]

        assert statuses[:5] == [401] * 5
        assert statuses[5] == 429
