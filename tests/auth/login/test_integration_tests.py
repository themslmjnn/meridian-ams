from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.repository import AuthRepository
from src.users.models.credentials import UserCredentials
from src.users.utils.enums import UserStatus
from src.utils import exceptions
from tests.auth.conftest import get_history, get_lockout
from tests.auth.constants import PASSWORD
from tests.endpoints import AuthEndpoints, UserEndpoints
from tests.factories import make_teacher


async def _login(client: AsyncClient, username: str, password: str = PASSWORD):
    return await client.post(
        AuthEndpoints.LOGIN,
        data={"username": username, "password": password},
    )


class TestSuccessfulLogin:
    async def test_returns_200_and_token(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        response = await _login(integration_client, teacher.username)

        data = response.json()

        assert response.status_code == 200
        assert set(data) == {"access_token", "token_type"}
        assert data["token_type"] == "bearer"
        assert data["access_token"]

    async def test_sets_httponly_cookies_and_keeps_refresh_token_out_of_body(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        response = await _login(integration_client, teacher.username)

        headers = response.headers.get_list("set-cookie")
        names = {h.split("=", 1)[0] for h in headers}

        assert names == {"refresh_token", "refresh_token_family", "device_id"}
        assert all("httponly" in h.lower() for h in headers)
        assert response.cookies["refresh_token"] not in response.text
        assert response.cookies["refresh_token_family"] not in response.text

    async def test_access_token_authenticates_protected_endpoint(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        login = await _login(integration_client, teacher.username)
        token = login.json()["access_token"]

        response = await integration_client.get(
            UserEndpoints.ME, headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

    async def test_writes_history_row(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        await _login(integration_client, teacher.username)

        history = await get_history(test_session, teacher.id)

        assert len(history) == 1
        assert history[0].success is True
        assert history[0].ip_address is not None

    async def test_second_login_with_device_cookie_reuses_session(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        first = await _login(integration_client, teacher.username)

        device_id = first.cookies["device_id"]
        count_after_first = await AuthRepository.get_session_count(
            test_session, teacher.id
        )

        integration_client.cookies.clear()
        integration_client.cookies.set("device_id", device_id)

        second = await _login(integration_client, teacher.username)

        count_after_second = await AuthRepository.get_session_count(
            test_session, teacher.id
        )

        assert second.status_code == 200
        assert count_after_second == count_after_first
        assert second.cookies["device_id"] == device_id


class TestFailedLogin:
    async def test_wrong_password_returns_401(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        response = await _login(integration_client, teacher.username, "wrong")

        lockout = await get_lockout(test_session, teacher.id)

        assert response.status_code == exceptions.InvalidCredentialsError().status_code
        assert response.status_code == 401
        assert lockout.failed_attempts == 1
        assert not response.headers.get_list("set-cookie")

    async def test_unknown_user_matches_wrong_password_response(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        wrong_password = await _login(integration_client, teacher.username, "wrong")
        unknown_user = await _login(integration_client, "no_such_user", "wrong")

        assert unknown_user.status_code == 401
        assert unknown_user.json() == wrong_password.json()

    async def test_locked_account_returns_lockout_error(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        lockout = await get_lockout(test_session, teacher.id)
        lockout.locked_until = datetime.now(UTC) + timedelta(minutes=10)

        await test_session.flush()

        expected = exceptions.AccountLockedError()

        response = await _login(integration_client, teacher.username)

        assert response.status_code == expected.status_code
        assert response.json()["error_code"] == expected.error_code

    async def test_pending_activation_rejected(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        teacher = await make_teacher(test_session, status=UserStatus.PENDING_ACTIVATION)

        expected = exceptions.AccountNotActivatedError()

        response = await _login(integration_client, teacher.username)

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
        teacher: UserCredentials,
        status,
    ):
        teacher = await make_teacher(test_session, status=status)

        expected = exceptions.AccessDeniedError()

        response = await _login(integration_client, teacher.username)

        assert response.status_code == expected.status_code
        assert response.json()["error_code"] == expected.error_code

    async def test_expired_deletion_grace_returns_401(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        teacher.status = UserStatus.PENDING_DELETION
        teacher.pre_transition_status = UserStatus.ACTIVE
        teacher.deletion_scheduled_for = datetime.now(UTC) - timedelta(minutes=1)

        await test_session.flush()

        response = await _login(integration_client, teacher.username)

        assert response.status_code == 401


class TestValidation:
    @pytest.mark.parametrize("missing", ["username", "password"])
    async def test_missing_form_field_returns_422(
        self, integration_client: AsyncClient, teacher: UserCredentials, missing
    ):
        data = {"username": teacher.username, "password": PASSWORD}
        del data[missing]

        response = await integration_client.post(AuthEndpoints.LOGIN, data=data)

        assert response.status_code == 422

    async def test_json_body_returns_422(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        response = await integration_client.post(
            AuthEndpoints.LOGIN,
            json={"username": teacher.username, "password": PASSWORD},
        )

        assert response.status_code == 422


from tests.auth.conftest import cookie_values

REFRESH_ENDPOINT = "/api/v1/auth/refresh-token"


def _cookie_header(cookies, names):
    return {"Cookie": "; ".join(f"{name}={cookies[name]}" for name in names)}


class TestLoginThenRefresh:
    async def test_new_device_cookies_can_refresh(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        login = await _login(integration_client, teacher.username)
        cookies = cookie_values(login.headers.get_list("set-cookie"))
        integration_client.cookies.clear()

        response = await integration_client.post(
            AuthEndpoints.REFRESH,
            headers=_cookie_header(cookies, ["refresh_token", "refresh_token_family"]),
        )

        assert response.status_code == 200

    async def test_known_device_cookies_can_refresh(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        first = await _login(integration_client, teacher.username)
        device_id = cookie_values(first.headers.get_list("set-cookie"))["device_id"]
        integration_client.cookies.clear()

        second = await integration_client.post(
            AuthEndpoints.LOGIN,
            data={"username": teacher.username, "password": PASSWORD},
            headers={"Cookie": f"device_id={device_id}"},
        )
        cookies = cookie_values(second.headers.get_list("set-cookie"))
        integration_client.cookies.clear()

        response = await integration_client.post(
            AuthEndpoints.REFRESH,
            headers=_cookie_header(cookies, ["refresh_token", "refresh_token_family"]),
        )

        assert second.status_code == 200
        assert cookies["device_id"] == device_id
        assert response.status_code == 200
