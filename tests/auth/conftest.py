from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.service import AuthService
from src.auth.tokens import sha256
from src.users.models.activation import UserActivation
from src.users.models.credentials import UserCredentials
from src.users.models.login_history import LoginHistory
from src.users.models.login_lockout import UserLoginLockout
from src.users.models.session import UserSession
from src.users.utils.enums import UserStatus
from tests.auth.constants import PASSWORD, RAW_ACTIVATION_TOKEN
from tests.factories import make_teacher


def make_request(cookies: dict[str, str] | None = None) -> Request:
    headers = []
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers.append((b"cookie", cookie_header.encode()))

    return Request({"type": "http", "headers": headers})


def make_form(username: str, password: str = PASSWORD) -> OAuth2PasswordRequestForm:
    return OAuth2PasswordRequestForm(username=username, password=password)


async def get_activation(
    session: AsyncSession, credentials_id: int
) -> UserActivation | None:
    query = (
        select(UserActivation)
        .where(UserActivation.credentials_id == credentials_id)
        .execution_options(populate_existing=True)
    )

    result = await session.execute(query)

    return result.scalar_one_or_none()


async def get_lockout(
    test_session: AsyncSession, credentials_id: int
) -> UserLoginLockout | None:
    query = (
        select(UserLoginLockout)
        .where(UserLoginLockout.credentials_id == credentials_id)
        .execution_options(populate_existing=True)
    )

    result = await test_session.execute(query)

    return result.scalar_one()


async def get_history(
    test_session: AsyncSession, credentials_id: int
) -> list[LoginHistory]:
    query = (
        select(LoginHistory)
        .where(LoginHistory.credentials_id == credentials_id)
        .order_by(LoginHistory.id)
    )

    result = await test_session.execute(query)

    return list(result.scalars().all())


async def get_sessions(
    test_session: AsyncSession, credentials_id: int
) -> list[UserSession]:
    query = (
        select(UserSession)
        .where(UserSession.credentials_id == credentials_id)
        .execution_options(populate_existing=True)
    )

    result = await test_session.execute(query)

    return list(result.scalars().all())


async def seed_sessions(
    test_session: AsyncSession,
    credentials_id: int,
    count: int,
) -> list[UserSession]:
    """Create `count` sessions; index 0 has the oldest `last_active_at`."""

    now = datetime.now(UTC)
    seeded = []

    for i in range(count):
        user_session = UserSession(
            credentials_id=credentials_id,
            refresh_token_hash=f"hash-{i}",
            refresh_token_family_hash=f"family-{i}",
            refresh_token_expires_at=now + timedelta(days=30),
            device_id=f"seed-device-{i}",
            last_active_at=now - timedelta(hours=count - i),
        )

        test_session.add(user_session)

        seeded.append(user_session)

    await test_session.flush()

    return seeded


def cookie_values(set_cookie_headers):
    values = {}
    for header in set_cookie_headers:
        name, rest = header.split("=", 1)
        values[name] = rest.split(";", 1)[0]

    return values


async def login_cookies(test_session: AsyncSession, credentials: UserCredentials):
    response = Response()

    await AuthService.login(
        response=response,
        request=make_request(),
        session=test_session,
        form_data=make_form(credentials.username),
        ip_address="203.0.113.7",
        user_agent="pytest-agent",
    )

    return cookie_values(response.headers.getlist("set-cookie"))


async def session_for_cookies(
    test_session: AsyncSession,
    credentials: UserCredentials,
    cookies,
):
    sessions = await get_sessions(test_session, credentials.id)

    return next(s for s in sessions if s.device_id == cookies["device_id"])


@pytest.fixture
def mock_auth_verify_password(mocker):
    return mocker.patch("src.auth.service.verify_password", new_callable=AsyncMock)


@pytest.fixture(autouse=True)
def mock_send_email_safe(mocker):
    return mocker.patch("src.auth.service.send_email_safe", new_callable=AsyncMock)


@pytest.fixture(autouse=True)
def mock_send_new_login_notification_email(mocker, mock_send_email_safe):
    return mocker.patch(
        "src.auth.service.send_new_login_notification_email",
        new_callable=MagicMock,
    )


@pytest.fixture(autouse=True)
def mock_send_guardian_account_reactivated_email(mocker, mock_send_email_safe):
    return mocker.patch(
        "src.auth.service.send_guardian_account_reactivated_email",
        new_callable=MagicMock,
    )


@pytest_asyncio.fixture
async def pending_user(test_session):
    teacher = await make_teacher(test_session)

    await test_session.execute(
        delete(UserActivation).where(UserActivation.credentials_id == teacher.id)
    )
    teacher.status = UserStatus.PENDING_ACTIVATION
    teacher.password_hash = None
    test_session.add(
        UserActivation(
            credentials_id=teacher.id,
            activation_token_hash=sha256(RAW_ACTIVATION_TOKEN),
            activation_token_expires_at=datetime.now(UTC) + timedelta(hours=72),
        )
    )
    await test_session.flush()

    return teacher
