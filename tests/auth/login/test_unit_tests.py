from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.repository import AuthRepository
from src.auth.service import AuthService
from src.core.config import get_settings
from src.emails.utils.enums import EmailType
from src.users.models.credentials import UserCredentials
from src.users.utils.enums import UserStatus
from src.utils import exceptions
from tests.auth.conftest import (
    get_history,
    get_lockout,
    get_sessions,
    make_form,
    make_request,
    seed_sessions,
)
from tests.auth.constants import IP, PASSWORD, USER_AGENT
from tests.endpoints import AuthEndpoints
from tests.factories import make_teacher

settings = get_settings()


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


async def _arrange_failure(test_session: AsyncSession, user: UserCredentials, scenario):
    if scenario == "wrong_password":
        return user.username, "wrong-password", exceptions.InvalidCredentialsError

    if scenario == "locked":
        lockout = await get_lockout(test_session, user.id)
        lockout.locked_until = datetime.now(UTC) + timedelta(minutes=10)

        await test_session.flush()

        return user.username, PASSWORD, exceptions.AccountLockedError

    if scenario == "pending_activation":
        user = await make_teacher(test_session, status=UserStatus.PENDING_ACTIVATION)

        return user.username, PASSWORD, exceptions.AccountNotActivatedError

    return "no_such_user", PASSWORD, exceptions.InvalidCredentialsError


class TestSuccessfulLogin:
    async def test_returns_bearer_token_with_expected_claims(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
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
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
    ):
        previous_sessions_count = await AuthRepository.get_session_count(
            test_session, teacher.id
        )
        response = Response()

        await _call_login(test_session, teacher.username, response=response)

        sessions = await get_sessions(test_session, teacher.id)
        device_id = _cookie_value(_set_cookies(response)["device_id"])
        created = next(s for s in sessions if s.device_id == device_id)

        assert len(sessions) == previous_sessions_count + 1
        assert created.refresh_token_hash
        assert created.refresh_token_family_hash
        assert created.refresh_token_expires_at > datetime.now(UTC)
        assert created.ip_address == IP
        assert created.user_agent == USER_AGENT

    async def test_writes_success_history_row(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
    ):
        await _call_login(test_session, teacher.username)

        history = await get_history(test_session, teacher.id)

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
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
        cookie_name,
        path,
    ):
        response = Response()

        await _call_login(test_session, teacher.username, response=response)

        header = _set_cookies(response)[cookie_name]

        assert "HttpOnly" in header
        assert "samesite=strict" in header.lower()
        assert f"Path={path}" in header
        assert (
            f"Max-Age={get_settings().REFRESH_TOKEN_EXPIRES_DAYS * 24 * 60 * 60}"
            in header
        )
        assert ("Secure" in header) == settings.COOKIE_SECURE

    async def test_resets_lockout_state(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
    ):
        lockout = await get_lockout(test_session, teacher.id)
        lockout.failed_attempts = settings.MAX_LOGIN_ATTEMPTS - 1
        lockout.last_failed_at = datetime.now(UTC)

        await test_session.flush()

        await _call_login(test_session, teacher.username)

        lockout = await get_lockout(test_session, teacher.id)

        assert lockout.failed_attempts == 0
        assert lockout.locked_until is None
        assert lockout.last_failed_at is None

    async def test_expired_lock_does_not_block_login(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
    ):
        lockout = await get_lockout(test_session, teacher.id)
        lockout.failed_attempts = settings.MAX_LOGIN_ATTEMPTS
        lockout.locked_until = datetime.now(UTC) - timedelta(minutes=1)

        await test_session.flush()

        result = await _call_login(test_session, teacher.username)
        lockout = await get_lockout(test_session, teacher.id)

        assert result.access_token
        assert lockout.failed_attempts == 0
        assert lockout.locked_until is None

    async def test_pending_deletion_within_grace_is_implicitly_cancelled(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
        mock_send_guardian_account_reactivated_email,
    ):
        teacher.status = UserStatus.PENDING_DELETION
        teacher.pre_transition_status = UserStatus.ACTIVE
        teacher.deletion_scheduled_for = datetime.now(UTC) + timedelta(days=5)

        await test_session.flush()

        result = await _call_login(test_session, teacher.username)

        assert result.access_token
        assert teacher.status == UserStatus.ACTIVE
        assert teacher.deletion_scheduled_for is None


class TestDeviceSessions:
    async def test_known_device_reuses_and_rotates_session(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
    ):
        existing = (await get_sessions(test_session, teacher.id))[0]
        existing.device_id = "known-device"
        existing.refresh_token_hash = "old-hash"
        existing.refresh_token_family_hash = "old-family"

        await test_session.flush()

        existing_id = existing.id
        before = await AuthRepository.get_session_count(test_session, teacher.id)
        response = Response()

        await _call_login(
            test_session,
            teacher.username,
            response=response,
            cookies={"device_id": "known-device"},
        )

        sessions = await get_sessions(test_session, teacher.id)
        reused = next(s for s in sessions if s.id == existing_id)

        assert len(sessions) == before
        assert reused.device_id == "known-device"
        assert reused.refresh_token_hash not in ("", "old-hash")
        assert reused.refresh_token_family_hash != "old-family"
        assert reused.ip_address == IP
        assert reused.user_agent == USER_AGENT
        assert reused.last_active_at is not None
        assert _cookie_value(_set_cookies(response)["device_id"]) == "known-device"

    async def test_unknown_device_cookie_creates_new_session(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
    ):
        sessions_count_before = await AuthRepository.get_session_count(
            test_session, teacher.id
        )
        response = Response()

        await _call_login(
            test_session,
            teacher.username,
            response=response,
            cookies={"device_id": "never-issued"},
        )

        sessions_count_after = await AuthRepository.get_session_count(
            test_session, teacher.id
        )

        assert sessions_count_after == sessions_count_before + 1
        assert _cookie_value(_set_cookies(response)["device_id"]) != "never-issued"

    async def test_device_id_of_another_user_is_ignored(
        self, test_session: AsyncSession, teacher: UserCredentials
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
            teacher.username,
            response=response,
            cookies={"device_id": "shared-device"},
        )

        other_sessions = await get_sessions(test_session, other.id)

        assert _cookie_value(_set_cookies(response)["device_id"]) != "shared-device"
        assert other_sessions[0].refresh_token_hash == "other-hash"

    async def test_session_cap_evicts_oldest_session(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
    ):
        await AuthRepository.delete_all_sessions(test_session, teacher.id)
        await seed_sessions(
            test_session, teacher.id, get_settings().MAX_SESSIONS_PER_USER
        )

        response = Response()

        await _call_login(test_session, teacher.username, response=response)

        sessions = await get_sessions(test_session, teacher.id)
        device_ids = {s.device_id for s in sessions}
        new_device_id = _cookie_value(_set_cookies(response)["device_id"])

        assert len(sessions) == get_settings().MAX_SESSIONS_PER_USER
        assert "seed-device-0" not in device_ids
        assert "seed-device-1" in device_ids
        assert new_device_id in device_ids

    async def test_below_cap_evicts_nothing(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
    ):
        sessions_before = await get_sessions(test_session, teacher.id)

        await _call_login(test_session, teacher.username)

        sessions_after = await get_sessions(test_session, teacher.id)

        assert {s.id for s in sessions_before} <= {s.id for s in sessions_after}


class TestUnknownUser:
    async def test_raises_invalid_credentials(self, test_session: AsyncSession):
        with pytest.raises(exceptions.InvalidCredentialsError):
            await _call_login(test_session, "no_such_user")

    async def test_still_verifies_a_password_hash(
        self, test_session: AsyncSession, mock_auth_verify_password
    ):
        with pytest.raises(exceptions.InvalidCredentialsError):
            await _call_login(test_session, "no_such_user", password="whatever")

        mock_auth_verify_password.assert_awaited_once()
        assert mock_auth_verify_password.await_args.args[0] == "whatever"


class TestWrongPassword:
    async def test_raises_and_records_failure(
        self, test_session: AsyncSession, teacher: UserCredentials
    ):
        response = Response()

        sessions_count_before = await AuthRepository.get_session_count(
            test_session, teacher.id
        )

        with pytest.raises(exceptions.InvalidCredentialsError):
            await _call_login(
                test_session, teacher.username, "wrong-password", response=response
            )

        lockout = await get_lockout(test_session, teacher.id)
        history = await get_history(test_session, teacher.id)

        assert lockout.failed_attempts == 1
        assert lockout.last_failed_at is not None
        assert lockout.locked_until is None
        assert len(history) == 1
        assert history[0].success is False
        assert history[0].failure_reason == "invalid_password"
        assert response.headers.getlist("set-cookie") == []
        assert (
            await AuthRepository.get_session_count(test_session, teacher.id)
            == sessions_count_before
        )

    async def test_reaching_max_attempts_locks_account(
        self, test_session: AsyncSession, teacher: UserCredentials
    ):
        lockout = await get_lockout(test_session, teacher.id)
        lockout.failed_attempts = settings.MAX_LOGIN_ATTEMPTS - 1

        await test_session.flush()

        with pytest.raises(exceptions.InvalidCredentialsError):
            await _call_login(test_session, teacher.username, "wrong-password")

        lockout = await get_lockout(test_session, teacher.id)
        expected = datetime.now(UTC) + timedelta(
            minutes=settings.LOCKOUT_DURATION_MINUTES
        )

        assert lockout.failed_attempts == settings.MAX_LOGIN_ATTEMPTS
        assert lockout.locked_until is not None
        assert abs((lockout.locked_until - expected).total_seconds()) < 5


class TestLockedAccount:
    async def test_correct_password_still_rejected(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
        mock_auth_verify_password,
    ):
        lockout = await get_lockout(test_session, teacher.id)

        lockout.failed_attempts = settings.MAX_LOGIN_ATTEMPTS
        lockout.locked_until = datetime.now(UTC) + timedelta(minutes=10)

        await test_session.flush()

        response = Response()

        with pytest.raises(exceptions.AccountLockedError):
            await _call_login(test_session, teacher.username, response=response)

        lockout = await get_lockout(test_session, teacher.id)
        history = await get_history(test_session, teacher.id)

        mock_auth_verify_password.assert_not_called()
        assert lockout.failed_attempts == settings.MAX_LOGIN_ATTEMPTS
        assert len(history) == 1
        assert history[0].success is False
        assert history[0].failure_reason == "account_locked"
        assert response.headers.getlist("set-cookie") == []


class TestAccountStatus:
    async def test_pending_activation_rejected(self, test_session: AsyncSession):
        teacher = await make_teacher(test_session, status=UserStatus.PENDING_ACTIVATION)

        with pytest.raises(exceptions.AccountNotActivatedError):
            await _call_login(test_session, teacher.username)

        history = await get_history(test_session, teacher.id)

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
        self, test_session: AsyncSession, teacher: UserCredentials, status
    ):
        teacher = await make_teacher(test_session, status=status)

        with pytest.raises(exceptions.AccessDeniedError):
            await _call_login(test_session, teacher.username)

        history = await get_history(test_session, teacher.id)

        assert [h.failure_reason for h in history] == [f"account_{status.value}"]
        assert history[0].success is False

    @pytest.mark.parametrize(
        "scheduled_for",
        [None, datetime.now(UTC) - timedelta(minutes=1)],
        ids=["no_schedule", "grace_expired"],
    )
    async def test_pending_deletion_with_expired_grace_rejected(
        self, test_session: AsyncSession, teacher: UserCredentials, scheduled_for
    ):
        teacher.status = UserStatus.PENDING_DELETION
        teacher.pre_transition_status = UserStatus.ACTIVE
        teacher.deletion_scheduled_for = scheduled_for

        await test_session.flush()

        with pytest.raises(exceptions.InvalidCredentialsError):
            await _call_login(test_session, teacher.username)

        history = await get_history(test_session, teacher.id)

        assert teacher.status == UserStatus.PENDING_DELETION
        assert [h.failure_reason for h in history] == ["deletion_grace_expired"]


class TestLoginEmails:
    async def test_new_device_queues_new_login_email(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
        mock_send_email_safe,
        mock_send_new_login_notification_email,
    ):
        login_time = datetime.now(UTC).strftime("%B %d, %Y at %H:%M UTC")

        await _call_login(test_session, teacher.username)

        mock_send_new_login_notification_email.assert_called_once_with(
            to_email=teacher.email,
            user_agent=USER_AGENT,
            login_time=login_time,
            password_reset_link=settings.APP_URL + AuthEndpoints.PASSWORD_RESET,
        )
        assert (
            mock_send_email_safe.call_args_list[0].kwargs["email_type"]
            == EmailType.NEW_LOGIN
        )

    async def test_known_device_queues_no_email(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
        mock_send_new_login_notification_email,
    ):
        existing = (await get_sessions(test_session, teacher.id))[0]
        existing.device_id = "known-device"

        await test_session.flush()

        await _call_login(
            test_session, teacher.username, cookies={"device_id": "known-device"}
        )

        mock_send_new_login_notification_email.assert_not_called()

    @pytest.mark.parametrize(
        "scenario",
        ["wrong_password", "locked", "pending_activation", "unknown_user"],
    )
    async def test_failed_login_queues_no_email(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
        scenario,
        mock_send_new_login_notification_email,
    ):
        username, password, expected = await _arrange_failure(
            test_session, teacher, scenario
        )

        with pytest.raises(expected):
            await _call_login(test_session, username, password)

        mock_send_new_login_notification_email.assert_not_called()

    async def test_active_login_queues_no_reactivation_email(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
        mock_send_guardian_account_reactivated_email,
    ):
        await _call_login(test_session, teacher.username)

        mock_send_guardian_account_reactivated_email.assert_not_called()


class TestImplicitDeletionCancel:
    async def test_cancellation_updates_account_and_queues_reactivation_email(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
        mock_send_email_safe,
        mock_send_guardian_account_reactivated_email,
    ):
        teacher.status = UserStatus.PENDING_DELETION
        teacher.deletion_scheduled_for = datetime.now(UTC) + timedelta(days=5)

        await test_session.flush()

        await _call_login(test_session, teacher.username)

        assert teacher.status == UserStatus.ACTIVE
        assert teacher.deletion_scheduled_for is None
        assert teacher.pre_transition_status == UserStatus.PENDING_DELETION
        assert (
            mock_send_email_safe.call_args_list[0].kwargs["email_type"]
            == EmailType.GUARDIAN_ACCOUNT_REACTIVATED
        )
        mock_send_guardian_account_reactivated_email.assert_called_once_with(
            to_email=teacher.email
        )

    async def test_wrong_password_does_not_cancel_deletion(
        self,
        test_session: AsyncSession,
        teacher: UserCredentials,
        mock_send_guardian_account_reactivated_email,
    ):
        scheduled_for = datetime.now(UTC) + timedelta(days=5)
        teacher.status = UserStatus.PENDING_DELETION
        teacher.deletion_scheduled_for = scheduled_for

        await test_session.flush()

        with pytest.raises(exceptions.InvalidCredentialsError):
            await _call_login(test_session, teacher.username, "wrong-password")

        lockout = await get_lockout(test_session, teacher.id)

        assert teacher.status == UserStatus.PENDING_DELETION
        assert teacher.deletion_scheduled_for == scheduled_for
        assert lockout.failed_attempts == 1
        mock_send_guardian_account_reactivated_email.assert_not_called()
