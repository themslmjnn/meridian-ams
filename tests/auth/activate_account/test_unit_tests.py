from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import ActivateAccount
from src.auth.service import AuthService
from src.core.security import verify_password, verify_token
from src.users.models.credentials import UserCredentials
from src.users.utils.enums import UserStatus
from src.users.utils.exceptions import UserNotPendingActivationError
from src.utils import exceptions
from tests.auth.conftest import cookie_values, get_activation, get_sessions
from tests.auth.constants import IP, NEW_PASSWORD, RAW_ACTIVATION_TOKEN, USER_AGENT
from tests.endpoints import AuthEndpoints


async def _activate(session: AsyncSession, payload, response=None):
    response = response if response is not None else Response()

    result = await AuthService.activate_account(
        response, session, payload, ip_address=IP, user_agent=USER_AGENT
    )

    return result, response


def _cookies_of(response: Response):
    return cookie_values(response.headers.getlist("set-cookie"))


async def _assert_nothing_changed(
    session: AsyncSession, user: UserCredentials, sessions_before, response
):
    sessions_after = await get_sessions(session, user.id)

    assert user.password_hash is None
    assert len(sessions_after) == sessions_before
    assert response.headers.getlist("set-cookie") == []


def make_payload(token=RAW_ACTIVATION_TOKEN, password=NEW_PASSWORD, confirm=None):
    return ActivateAccount(
        activation_token=token,
        new_password=password,
        confirm_password=confirm if confirm is not None else password,
    )


class TestSuccessfulActivation:
    async def test_returns_bearer_token_with_expected_claims(
        self, test_session: AsyncSession, pending_user: UserCredentials
    ):
        result, response = await _activate(test_session, make_payload())

        cookies = _cookies_of(response)
        sessions = await get_sessions(test_session, pending_user.id)
        created = next(s for s in sessions if s.device_id == cookies["device_id"])
        claims = jwt.decode(result.access_token, options={"verify_signature": False})

        assert result.token_type == "bearer"
        assert claims["sub"] == str(pending_user.public_id)
        assert claims["role"] == pending_user.role
        assert claims["session_id"] == created.id

    async def test_activates_account_and_sets_hashed_password(
        self, test_session: AsyncSession, pending_user: UserCredentials
    ):
        await _activate(test_session, make_payload())

        assert pending_user.status == UserStatus.ACTIVE
        assert pending_user.password_hash != NEW_PASSWORD
        assert await verify_password(NEW_PASSWORD, pending_user.password_hash)

    async def test_consumes_activation_row(
        self, test_session: AsyncSession, pending_user: UserCredentials
    ):
        await _activate(test_session, make_payload())

        assert await get_activation(test_session, pending_user.id) is None

    async def test_creates_session_with_hashed_tokens(
        self, test_session: AsyncSession, pending_user: UserCredentials
    ):
        before = len(await get_sessions(test_session, pending_user.id))

        _, response = await _activate(test_session, make_payload())

        cookies = _cookies_of(response)
        sessions = await get_sessions(test_session, pending_user.id)
        created = next(s for s in sessions if s.device_id == cookies["device_id"])

        assert len(sessions) == before + 1
        assert verify_token(cookies["refresh_token"], created.refresh_token_hash)
        assert verify_token(
            cookies["refresh_token_family"], created.refresh_token_family_hash
        )
        assert created.refresh_token_family_hash != cookies["refresh_token_family"]
        assert created.refresh_token_expires_at > datetime.now(UTC)
        assert created.ip_address == IP
        assert created.user_agent == USER_AGENT

    @pytest.mark.parametrize(
        ("cookie_name", "path"),
        [
            ("refresh_token", AuthEndpoints.REFRESH),
            ("refresh_token_family", AuthEndpoints.REFRESH),
            ("device_id", AuthEndpoints.LOGIN),
        ],
    )
    async def test_cookie_attributes(
        self, test_session: AsyncSession, pending_user, cookie_name, path
    ):
        _, response = await _activate(test_session, make_payload())

        headers = {
            h.split("=", 1)[0]: h for h in response.headers.getlist("set-cookie")
        }

        assert set(headers) == {"refresh_token", "refresh_token_family", "device_id"}
        assert "HttpOnly" in headers[cookie_name]
        assert "samesite=strict" in headers[cookie_name].lower()
        assert f"Path={path}" in headers[cookie_name]

    async def test_returned_cookies_can_refresh(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        pending_user: UserCredentials,
    ):
        _, response = await _activate(test_session, make_payload())
        cookies = _cookies_of(response)

        result = await AuthService.refresh_token(
            Response(),
            test_session,
            redis_client,
            cookies["refresh_token"],
            cookies["refresh_token_family"],
        )

        assert result.access_token


class TestRejectedActivation:
    async def test_unknown_token_rejected(
        self, test_session: AsyncSession, pending_user: UserCredentials
    ):
        before = len(await get_sessions(test_session, pending_user.id))
        response = Response()

        with pytest.raises(exceptions.InvalidActivationTokenError):
            await _activate(test_session, make_payload(token="no-such-token"), response)

        await _assert_nothing_changed(test_session, pending_user, before, response)
        assert pending_user.status == UserStatus.PENDING_ACTIVATION

    async def test_expired_token_rejected_and_row_kept(
        self, test_session: AsyncSession, pending_user: UserCredentials
    ):
        activation = await get_activation(test_session, pending_user.id)
        activation.activation_token_expires_at = datetime.now(UTC) - timedelta(
            minutes=1
        )
        await test_session.flush()
        before = len(await get_sessions(test_session, pending_user.id))
        response = Response()

        with pytest.raises(exceptions.ExpiredActivationTokenError):
            await _activate(test_session, make_payload(), response)

        await _assert_nothing_changed(test_session, pending_user, before, response)
        assert pending_user.status == UserStatus.PENDING_ACTIVATION
        assert await get_activation(test_session, pending_user.id) is not None

    @pytest.mark.parametrize(
        "status",
        [UserStatus.ACTIVE, UserStatus.DEACTIVATED, UserStatus.PENDING_DELETION],
    )
    async def test_non_pending_status_rejected(
        self, test_session: AsyncSession, pending_user: UserCredentials, status
    ):
        pending_user.status = status
        await test_session.flush()
        before = len(await get_sessions(test_session, pending_user.id))
        response = Response()

        with pytest.raises(UserNotPendingActivationError):
            await _activate(test_session, make_payload(), response)

        await _assert_nothing_changed(test_session, pending_user, before, response)
        assert pending_user.status == status

    async def test_lost_concurrent_claim_rejected(
        self, test_session: AsyncSession, pending_user: UserCredentials, mocker
    ):
        mocker.patch(
            "src.auth.service.AuthRepository.claim_activation_token",
            new_callable=mocker.AsyncMock,
            return_value=False,
        )
        before = len(await get_sessions(test_session, pending_user.id))
        response = Response()

        with pytest.raises(exceptions.InvalidActivationTokenError):
            await _activate(test_session, make_payload(), response)

        await _assert_nothing_changed(test_session, pending_user, before, response)
        assert pending_user.status == UserStatus.PENDING_ACTIVATION

    async def test_reused_token_rejected(
        self, test_session: AsyncSession, pending_user: UserCredentials
    ):
        await _activate(test_session, make_payload())
        before = len(await get_sessions(test_session, pending_user.id))
        response = Response()

        with pytest.raises(exceptions.InvalidActivationTokenError):
            await _activate(
                test_session, make_payload(password="An0ther!Passw0rd#1"), response
            )

        assert len(await get_sessions(test_session, pending_user.id)) == before
        assert await verify_password(NEW_PASSWORD, pending_user.password_hash)
        assert response.headers.getlist("set-cookie") == []
