from datetime import UTC, datetime, timedelta

import pytest_asyncio
from fastapi import Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.users.models.login_history import LoginHistory
from src.users.models.login_lockout import UserLoginLockout
from src.users.models.session import UserSession
from src.users.utils.enums import UserStatus
from tests.factories import make_teacher

PASSWORD = "Str0ng!Passw0rd"


def make_request(cookies: dict[str, str] | None = None) -> Request:
    headers = []
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers.append((b"cookie", cookie_header.encode()))

    return Request({"type": "http", "headers": headers})


def make_form(username: str, password: str = PASSWORD) -> OAuth2PasswordRequestForm:
    return OAuth2PasswordRequestForm(username=username, password=password)


async def prepare_for_login(
    session: AsyncSession, credentials, status=UserStatus.ACTIVE
):
    credentials.password_hash = await hash_password(PASSWORD)
    credentials.status = status
    await session.flush()

    return credentials


async def get_lockout(session: AsyncSession, credentials_id: int) -> UserLoginLockout:
    result = await session.execute(
        select(UserLoginLockout)
        .where(UserLoginLockout.credentials_id == credentials_id)
        .execution_options(populate_existing=True)
    )

    return result.scalar_one()


async def get_history(session: AsyncSession, credentials_id: int) -> list[LoginHistory]:
    result = await session.execute(
        select(LoginHistory)
        .where(LoginHistory.credentials_id == credentials_id)
        .order_by(LoginHistory.id)
    )

    return list(result.scalars().all())


async def get_sessions(session: AsyncSession, credentials_id: int) -> list[UserSession]:
    result = await session.execute(
        select(UserSession)
        .where(UserSession.credentials_id == credentials_id)
        .execution_options(populate_existing=True)
    )

    return list(result.scalars().all())


async def seed_sessions(
    session: AsyncSession, credentials_id: int, count: int
) -> list[UserSession]:
    """Create `count` sessions; index 0 has the oldest `last_active_at`."""
    now = datetime.now(UTC)
    seeded = []

    for i in range(count):
        user_session = UserSession(
            credentials_id=credentials_id,
            refresh_token_hash=f"hash-{i}",
            refresh_token_family=f"family-{i}",
            refresh_token_expires_at=now + timedelta(days=30),
            device_id=f"seed-device-{i}",
            last_active_at=now - timedelta(hours=count - i),
        )
        session.add(user_session)
        seeded.append(user_session)

    await session.flush()

    return seeded


@pytest_asyncio.fixture
async def login_user(test_session):
    teacher = await make_teacher(test_session)

    return await prepare_for_login(test_session, teacher)
