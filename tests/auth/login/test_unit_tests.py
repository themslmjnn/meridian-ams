from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import Response
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.repository import AuthRepository
from src.auth.service import AuthService
from src.core.config import get_settings
from src.users.models.credentials import UserCredentials
from src.users.models.session import UserSession
from src.users.utils.enums import UserStatus
from src.utils import exceptions
from tests.auth.conftest import (
    PASSWORD,
    get_history,
    get_lockout,
    get_sessions,
    make_form,
    make_request,
    prepare_for_login,
    seed_sessions,
)
from tests.factories import make_teacher

settings = get_settings()

IP = "203.0.113.7"
USER_AGENT = "pytest-agent"


async def _call_login(
    session: AsyncSession,
    username: str,
    password: str = PASSWORD,
    response: str = None,
    cookies: dict[str, str] | None = None,
):
    return await AuthService.login(
        response=response if response is not None else Response(),
        request=make_request(cookies),
        session=session,
        form_data=make_form(username, password),
        ip_address=IP,
        user_agent=USER_AGENT,
    )


def _set_cookies(response: Response) -> dict[str, str]:
    """Map cookie name -> full Set-Cookie header."""

    return {
        header.split("=", 1)[0]: header
        for header in response.headers.getlist("set-cookie")
    }


def _cookie_value(header: str) -> str:
    return header.split(";", 1)[0].split("=", 1)[1]


class TestSuccessfulLogin:
    async def test_returns_bearer_token_with_expected_claims(
        self, test_session: AsyncSession, teacher: UserCredentials
    ):
        result = await _call_login(test_session, teacher.username)

        sessions = await get_sessions(test_session, teacher.id)
        claims = jwt.decode(result.access_token, options={"verify_signature": False})

        assert result.token_type == "bearer"
        assert claims["sub"] == str(teacher.public_id)
        assert claims["role"] == teacher.role
        assert claims["account_type"] == teacher.account_type
        assert claims["session_id"] in {s.id for s in sessions}

    async def test_new_device_creates_session(
        self, test_session: AsyncSession, login_user
    ):
        before = await AuthRepository.get_session_count(test_session, login_user.id)
        response = Response()

        await _call_login(test_session, login_user.username, response=response)

        sessions = await get_sessions(test_session, login_user.id)
        device_id = _cookie_value(_set_cookies(response)["device_id"])
        created = next(s for s in sessions if s.device_id == device_id)

        assert len(sessions) == before + 1
        assert created.refresh_token_hash
        assert created.refresh_token_family
        assert created.refresh_token_expires_at > datetime.now(UTC)
        assert created.ip_address == IP
        assert created.user_agent == USER_AGENT

    async def test_writes_success_history_row(
        self, test_session: AsyncSession, login_user
    ):
        await _call_login(test_session, login_user.username)

        history = await get_history(test_session, login_user.id)

        assert len(history) == 1
        assert history[0].success is True
        assert history[0].failure_reason is None
        assert history[0].ip_address == IP
        assert history[0].user_agent == USER_AGENT

    @pytest.mark.parametrize(
        ("cookie_name", "path"),
        [
            ("refresh_token", "/api/v1/auth/refresh-token"),
            ("refresh_token_family", "/api/v1/auth/refresh-token"),
            ("device_id", "/api/v1/auth/login"),
        ],
    )
    async def test_cookie_attributes(
        self, test_session: AsyncSession, login_user, cookie_name, path
    ):
        response = Response()

        await _call_login(test_session, login_user.username, response=response)

        header = _set_cookies(response)[cookie_name]

        assert "HttpOnly" in header
        assert "samesite=strict" in header.lower()
        assert f"Path={path}" in header
        assert f"Max-Age={get_settings().REFRESH_TOKEN_EXPIRES_DAYS}" in header
        assert ("Secure" in header) == settings.COOKIE_SECURE

    async def test_resets_lockout_state(self, test_session: AsyncSession, login_user):
        lockout = await get_lockout(test_session, login_user.id)
        lockout.failed_attempts = settings.MAX_LOGIN_ATTEMPTS - 1
        lockout.last_failed_at = datetime.now(UTC)
        await test_session.flush()

        await _call_login(test_session, login_user.username)

        lockout = await get_lockout(test_session, login_user.id)

        assert lockout.failed_attempts == 0
        assert lockout.locked_until is None
        assert lockout.last_failed_at is None

    async def test_expired_lock_does_not_block_login(
        self, test_session: AsyncSession, login_user
    ):
        lockout = await get_lockout(test_session, login_user.id)
        lockout.failed_attempts = settings.MAX_LOGIN_ATTEMPTS
        lockout.locked_until = datetime.now(UTC) - timedelta(minutes=1)
        await test_session.flush()

        result = await _call_login(test_session, login_user.username)
        lockout = await get_lockout(test_session, login_user.id)

        assert result.access_token
        assert lockout.failed_attempts == 0
        assert lockout.locked_until is None

    async def test_pending_deletion_within_grace_is_implicitly_cancelled(
        self, test_session: AsyncSession, login_user
    ):
        login_user.status = UserStatus.PENDING_DELETION
        login_user.pre_transition_status = UserStatus.ACTIVE
        login_user.deletion_scheduled_for = datetime.now(UTC) + timedelta(days=5)
        await test_session.flush()

        result = await _call_login(test_session, login_user.username)

        assert result.access_token
        assert login_user.status == UserStatus.ACTIVE
        assert login_user.deletion_scheduled_for is None


class TestDeviceSessions:
    async def test_known_device_reuses_and_rotates_session(
        self, test_session: AsyncSession, login_user
    ):
        existing = (await get_sessions(test_session, login_user.id))[0]
        existing.device_id = "known-device"
        existing.refresh_token_hash = "old-hash"
        existing.refresh_token_family = "old-family"
        existing.previous_refresh_token_hash = "old-previous-hash"
        existing.rotated_at = datetime.now(UTC)

        await test_session.flush()

        existing_id = existing.id
        before = await AuthRepository.get_session_count(test_session, login_user.id)
        response = Response()

        await _call_login(
            test_session,
            login_user.username,
            response=response,
            cookies={"device_id": "known-device"},
        )

        sessions = await get_sessions(test_session, login_user.id)
        reused = next(s for s in sessions if s.id == existing_id)

        assert len(sessions) == before
        assert reused.device_id == "known-device"
        assert reused.refresh_token_hash not in ("", "old-hash")
        assert reused.refresh_token_family != "old-family"
        assert reused.previous_refresh_token_hash is None
        assert reused.rotated_at is None
        assert reused.ip_address == IP
        assert reused.user_agent == USER_AGENT
        assert reused.last_active_at is not None
        assert _cookie_value(_set_cookies(response)["device_id"]) == "known-device"

    async def test_unknown_device_cookie_creates_new_session(
        self, test_session: AsyncSession, login_user
    ):
        before = await AuthRepository.get_session_count(test_session, login_user.id)
        response = Response()

        await _call_login(
            test_session,
            login_user.username,
            response=response,
            cookies={"device_id": "never-issued"},
        )

        after = await AuthRepository.get_session_count(test_session, login_user.id)

        assert after == before + 1
        assert _cookie_value(_set_cookies(response)["device_id"]) != "never-issued"

    async def test_device_id_of_another_user_is_ignored(
        self, test_session: AsyncSession, login_user
    ):
        other = await make_teacher(
            test_session,
            username="other_teacher",
            email="other.teacher@meridian.edu",
        )
        other_session = (await get_sessions(test_session, other.id))[0]
        other_session.device_id = "shared-device"
        other_session.refresh_token_hash = "other-hash"

        await test_session.flush()

        response = Response()

        await _call_login(
            test_session,
            login_user.username,
            response=response,
            cookies={"device_id": "shared-device"},
        )

        other_sessions = await get_sessions(test_session, other.id)

        assert _cookie_value(_set_cookies(response)["device_id"]) != "shared-device"
        assert other_sessions[0].refresh_token_hash == "other-hash"

    async def test_session_cap_evicts_oldest_session(
        self, test_session: AsyncSession, login_user
    ):
        await test_session.execute(
            delete(UserSession).where(UserSession.credentials_id == login_user.id)
        )
        await seed_sessions(
            test_session, login_user.id, get_settings().MAX_SESSIONS_PER_USER
        )
        response = Response()

        await _call_login(test_session, login_user.username, response=response)

        sessions = await get_sessions(test_session, login_user.id)
        device_ids = {s.device_id for s in sessions}
        new_device_id = _cookie_value(_set_cookies(response)["device_id"])

        assert len(sessions) == get_settings().MAX_SESSIONS_PER_USER
        assert "seed-device-0" not in device_ids
        assert "seed-device-1" in device_ids
        assert new_device_id in device_ids

    async def test_below_cap_evicts_nothing(
        self, test_session: AsyncSession, login_user
    ):
        before = await get_sessions(test_session, login_user.id)

        await _call_login(test_session, login_user.username)

        after = await get_sessions(test_session, login_user.id)

        assert {s.id for s in before} <= {s.id for s in after}


class TestUnknownUser:
    async def test_raises_invalid_credentials(self, test_session: AsyncSession):
        with pytest.raises(exceptions.InvalidCredentialsError):
            await _call_login(test_session, "no_such_user")

    async def test_still_verifies_a_password_hash(
        self, test_session: AsyncSession, mocker
    ):
        verify = mocker.patch(
            "src.auth.service.verify_password",
            new_callable=AsyncMock,
            return_value=False,
        )

        with pytest.raises(exceptions.InvalidCredentialsError):
            await _call_login(test_session, "no_such_user", password="whatever")

        verify.assert_awaited_once()
        assert verify.await_args.args[0] == "whatever"


class TestWrongPassword:
    async def test_raises_and_records_failure(
        self, test_session: AsyncSession, login_user
    ):
        response = Response()
        before = await AuthRepository.get_session_count(test_session, login_user.id)

        with pytest.raises(exceptions.InvalidCredentialsError):
            await _call_login(
                test_session, login_user.username, "wrong-password", response=response
            )

        lockout = await get_lockout(test_session, login_user.id)
        history = await get_history(test_session, login_user.id)

        assert lockout.failed_attempts == 1
        assert lockout.last_failed_at is not None
        assert lockout.locked_until is None
        assert len(history) == 1
        assert history[0].success is False
        assert history[0].failure_reason == "invalid_password"
        assert response.headers.getlist("set-cookie") == []
        assert (
            await AuthRepository.get_session_count(test_session, login_user.id)
            == before
        )

    async def test_reaching_max_attempts_locks_account(
        self, test_session: AsyncSession, login_user
    ):
        lockout = await get_lockout(test_session, login_user.id)
        lockout.failed_attempts = settings.MAX_LOGIN_ATTEMPTS - 1

        await test_session.flush()

        with pytest.raises(exceptions.InvalidCredentialsError):
            await _call_login(test_session, login_user.username, "wrong-password")

        lockout = await get_lockout(test_session, login_user.id)
        expected = datetime.now(UTC) + timedelta(
            minutes=settings.LOCKOUT_DURATION_MINUTES
        )

        assert lockout.failed_attempts == settings.MAX_LOGIN_ATTEMPTS
        assert lockout.locked_until is not None
        assert abs((lockout.locked_until - expected).total_seconds()) < 5


class TestLockedAccount:
    async def test_correct_password_still_rejected(
        self, test_session: AsyncSession, login_user, mocker
    ):
        lockout = await get_lockout(test_session, login_user.id)

        lockout.failed_attempts = settings.MAX_LOGIN_ATTEMPTS
        lockout.locked_until = datetime.now(UTC) + timedelta(minutes=10)

        await test_session.flush()

        verify = mocker.patch(
            "src.auth.service.verify_password", new_callable=AsyncMock
        )
        response = Response()

        with pytest.raises(exceptions.AccountLockedError):
            await _call_login(test_session, login_user.username, response=response)

        lockout = await get_lockout(test_session, login_user.id)
        history = await get_history(test_session, login_user.id)

        verify.assert_not_called()
        assert lockout.failed_attempts == settings.MAX_LOGIN_ATTEMPTS
        assert len(history) == 1
        assert history[0].success is False
        assert history[0].failure_reason == "account_locked"
        assert response.headers.getlist("set-cookie") == []


class TestAccountStatus:
    async def test_pending_activation_rejected(
        self, test_session: AsyncSession, login_user
    ):
        await prepare_for_login(test_session, login_user, UserStatus.PENDING_ACTIVATION)

        with pytest.raises(exceptions.AccountInactiveError):
            await _call_login(test_session, login_user.username)

        history = await get_history(test_session, login_user.id)

        assert [h.failure_reason for h in history] == ["account_not_activated"]
        assert history[0].success is False

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
        self, test_session: AsyncSession, login_user, status
    ):
        await prepare_for_login(test_session, login_user, status)

        with pytest.raises(exceptions.AccessDeniedError):
            await _call_login(test_session, login_user.username)

        history = await get_history(test_session, login_user.id)

        assert [h.failure_reason for h in history] == [f"account_{status.value}"]
        assert history[0].success is False

    @pytest.mark.parametrize(
        "scheduled_for",
        [None, datetime.now(UTC) - timedelta(minutes=1)],
        ids=["no_schedule", "grace_expired"],
    )
    async def test_pending_deletion_with_expired_grace_rejected(
        self, test_session: AsyncSession, login_user, scheduled_for
    ):
        login_user.status = UserStatus.PENDING_DELETION
        login_user.pre_transition_status = UserStatus.ACTIVE
        login_user.deletion_scheduled_for = scheduled_for

        await test_session.flush()

        with pytest.raises(exceptions.InvalidCredentialsError):
            await _call_login(test_session, login_user.username)

        history = await get_history(test_session, login_user.id)

        assert login_user.status == UserStatus.PENDING_DELETION
        assert [h.failure_reason for h in history] == ["deletion_grace_expired"]
