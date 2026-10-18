from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.utils.enums import UserStatus
from src.utils import exceptions
from tests.auth.conftest import PASSWORD, cookie_values, get_sessions
from tests.endpoints import AuthEndpoints, UserEndpoints


async def _login(client: AsyncClient, teacher: UserCredentials):
    response = await client.post(
        AuthEndpoints.LOGIN,
        data={"username": teacher.username, "password": PASSWORD},
    )

    cookies = cookie_values(response.headers.get_list("set-cookie"))

    client.cookies.clear()

    return response.json()["access_token"], cookies


def _cookie_header(cookies):
    return {
        "Cookie": (
            f"refresh_token={cookies['refresh_token']}; "
            f"refresh_token_family={cookies['refresh_token_family']}"
        )
    }


async def _refresh(client: AsyncClient, cookies):
    return await client.post(AuthEndpoints.REFRESH, headers=_cookie_header(cookies))


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


class TestMissingCookies:
    @pytest.mark.parametrize(
        "present",
        [[], ["refresh_token"], ["refresh_token_family"]],
        ids=["none", "token_only", "family_only"],
    )
    async def test_missing_cookie_returns_401(
        self,
        integration_client: AsyncClient,
        teacher: UserCredentials,
        present,
    ):
        _, cookies = await _login(integration_client, teacher)
        header = "; ".join(f"{name}={cookies[name]}" for name in present)

        response = await integration_client.post(
            AuthEndpoints.REFRESH, headers={"Cookie": header} if header else {}
        )

        assert response.status_code == exceptions.InvalidRefreshTokenError().status_code
        assert response.status_code == 401


class TestSuccessfulRefresh:
    async def test_returns_200_and_token(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        _, cookies = await _login(integration_client, teacher)

        response = await _refresh(integration_client, cookies)

        data = response.json()

        assert response.status_code == 200
        assert set(data) == {"access_token", "token_type"}
        assert data["token_type"] == "bearer"
        assert data["access_token"]

    async def test_rotates_token_cookie_and_keeps_family(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        _, cookies = await _login(integration_client, teacher)

        response = await _refresh(integration_client, cookies)

        headers = response.headers.get_list("set-cookie")
        rotated = cookie_values(headers)

        assert set(rotated) == {"refresh_token", "refresh_token_family"}
        assert rotated["refresh_token"] != cookies["refresh_token"]
        assert rotated["refresh_token_family"] == cookies["refresh_token_family"]
        assert rotated["refresh_token"] not in response.text
        for header in headers:
            assert "httponly" in header.lower()
            assert f"path={AuthEndpoints.REFRESH}".lower() in header.lower()

    async def test_new_access_token_authenticates_protected_endpoint(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        _, cookies = await _login(integration_client, teacher)

        refreshed = await _refresh(integration_client, cookies)
        response = await integration_client.get(
            UserEndpoints.ME, headers=_bearer(refreshed.json()["access_token"])
        )

        assert response.status_code == 200

    async def test_rotated_cookies_can_refresh_again(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        _, cookies = await _login(integration_client, teacher)
        first = await _refresh(integration_client, cookies)
        rotated = cookie_values(first.headers.get_list("set-cookie"))

        second = await _refresh(integration_client, rotated)

        assert second.status_code == 200


class TestRejectedRefresh:
    async def test_replayed_cookies_return_401_and_kill_rotated_cookies(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        _, original = await _login(integration_client, teacher)
        first = await _refresh(integration_client, original)
        rotated = cookie_values(first.headers.get_list("set-cookie"))

        replay = await _refresh(integration_client, original)
        after_replay = await _refresh(integration_client, rotated)

        assert first.status_code == 200
        assert replay.status_code == 401
        assert after_replay.status_code == 401

    async def test_replay_invalidates_issued_access_token(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        access_token, original = await _login(integration_client, teacher)
        await _refresh(integration_client, original)

        await _refresh(integration_client, original)
        response = await integration_client.get(
            UserEndpoints.ME, headers=_bearer(access_token)
        )

        assert response.status_code == 401

    async def test_wrong_family_returns_401_and_kills_session(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        _, cookies = await _login(integration_client, teacher)

        wrong = await _refresh(
            integration_client, {**cookies, "refresh_token_family": "wrong-family"}
        )
        genuine = await _refresh(integration_client, cookies)

        assert wrong.status_code == 401
        assert genuine.status_code == 401

    async def test_garbage_token_returns_401(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        _, cookies = await _login(integration_client, teacher)
        expected = exceptions.InvalidRefreshTokenError()

        response = await _refresh(
            integration_client, {**cookies, "refresh_token": "not-a-jwt"}
        )

        assert response.status_code == expected.status_code
        assert response.json()["error_code"] == expected.error_code

    async def test_expired_session_returns_expired_error(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        _, cookies = await _login(integration_client, teacher)
        sessions = await get_sessions(test_session, teacher.id)

        current = next(s for s in sessions if s.device_id == cookies["device_id"])

        current.refresh_token_expires_at = datetime.now(UTC) - timedelta(minutes=1)

        await test_session.flush()

        expected = exceptions.ExpiredRefreshTokenError()

        response = await _refresh(integration_client, cookies)

        assert response.status_code == expected.status_code
        assert response.json()["error_code"] == expected.error_code

    async def test_refresh_after_logout_returns_401(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        access_token, cookies = await _login(integration_client, teacher)

        await integration_client.post(
            AuthEndpoints.LOGOUT, headers=_bearer(access_token)
        )

        response = await _refresh(integration_client, cookies)

        assert response.status_code == 401

    async def test_deactivated_account_returns_mapped_error(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        _, cookies = await _login(integration_client, teacher)

        teacher.status = UserStatus.DEACTIVATED

        await test_session.flush()

        expected = exceptions.AccountInactiveError()

        response = await _refresh(integration_client, cookies)

        assert response.status_code == expected.status_code
        assert response.json()["error_code"] == expected.error_code


class TestRateLimit:
    async def test_thirty_first_request_within_a_minute_returns_429(
        self, integration_client: AsyncClient
    ):
        statuses = [
            (await integration_client.post(AuthEndpoints.REFRESH)).status_code
            for _ in range(31)
        ]

        assert statuses[:30] == [401] * 30
        assert statuses[30] == 429
