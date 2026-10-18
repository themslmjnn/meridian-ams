import secrets
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import Response
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.service import AuthService
from src.auth.tokens import create_refresh_token
from src.core.config import get_settings
from src.core.security import generate_token, verify_token
from src.users.models.credentials import UserCredentials
from src.users.models.session import UserSession
from src.users.utils.enums import UserStatus
from src.utils import exceptions
from src.utils.cache_keys import SessionCacheKey
from tests.auth.conftest import (
    cookie_values,
    get_sessions,
    seed_sessions,
)

settings = get_settings()


async def _login_cookies(session: AsyncSession, teacher: UserCredentials):
    raw_refresh_token_family, hashed_refresh_token_family = generate_token()

    user_session = UserSession(
        credentials_id=teacher.id,
        refresh_token_hash="",
        refresh_token_family_hash=hashed_refresh_token_family,
        refresh_token_expires_at=datetime.now(UTC)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRES_DAYS),
        device_id=secrets.token_urlsafe(32),
    )
    session.add(user_session)
    await session.flush()

    raw_refresh_token, hashed_refresh_token = create_refresh_token(
        public_id=teacher.public_id, session_id=user_session.id
    )
    user_session.refresh_token_hash = hashed_refresh_token

    await session.flush()

    return {
        "refresh_token": raw_refresh_token,
        "refresh_token_family": raw_refresh_token_family,
        "device_id": user_session.device_id,
    }


async def _session_for(
    session: AsyncSession, teacher: UserCredentials, cookies
) -> UserSession:
    sessions = await get_sessions(session, teacher.id)

    return next(s for s in sessions if s.device_id == cookies["device_id"])


async def _refresh(session: AsyncSession, redis: Redis, cookies, response=None):
    response = response if response is not None else Response()

    result = await AuthService.refresh_token(
        response,
        session,
        redis,
        cookies["refresh_token"],
        cookies["refresh_token_family"],
    )

    return result, response


async def _rotate(session: AsyncSession, redis: Redis, teacher: UserCredentials):
    original = await _login_cookies(session, teacher)
    _, response = await _refresh(session, redis, original)
    rotated = cookie_values(response.headers.getlist("set-cookie"))

    assert rotated["refresh_token"] != original["refresh_token"]

    return original, rotated


async def _is_revoked(session: AsyncSession, session_id):
    result = await session.execute(
        select(UserSession)
        .where(UserSession.id == session_id)
        .execution_options(populate_existing=True)
    )

    row = result.scalar_one_or_none()

    return row is None or row.refresh_token_hash is None


async def _seed_version_key(redis: Redis, session_id):
    key = SessionCacheKey.access_token_version_key(session_id)

    await redis.set(key, "1")

    return key


class TestSuccessfulRotation:
    async def test_returns_bearer_token_with_expected_claims(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        cookies = await _login_cookies(test_session, teacher)
        current = await _session_for(test_session, teacher, cookies)

        result, _ = await _refresh(test_session, redis_client, cookies)

        claims = jwt.decode(result.access_token, options={"verify_signature": False})

        assert result.token_type == "bearer"
        assert claims["sub"] == str(teacher.public_id)
        assert claims["session_id"] == current.id

    async def test_rotates_session_state(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        cookies = await _login_cookies(test_session, teacher)
        current = await _session_for(test_session, teacher, cookies)

        old_hash = current.refresh_token_hash
        old_family_hash = current.refresh_token_family_hash

        _, response = await _refresh(test_session, redis_client, cookies)

        rotated = cookie_values(response.headers.getlist("set-cookie"))
        current = await _session_for(test_session, teacher, cookies)

        expected_expiry = datetime.now(UTC) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRES_DAYS
        )

        assert current.refresh_token_hash != old_hash
        assert verify_token(rotated["refresh_token"], current.refresh_token_hash)
        assert current.refresh_token_family_hash == old_family_hash
        assert current.last_active_at is not None
        assert (
            abs((current.refresh_token_expires_at - expected_expiry).total_seconds())
            < 5
        )

    async def test_sets_new_token_and_keeps_family_cookie(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        cookies = await _login_cookies(test_session, teacher)

        _, response = await _refresh(test_session, redis_client, cookies)

        rotated = cookie_values(response.headers.getlist("set-cookie"))

        assert set(rotated) == {"refresh_token", "refresh_token_family"}
        assert rotated["refresh_token"] != cookies["refresh_token"]
        assert rotated["refresh_token_family"] == cookies["refresh_token_family"]

    async def test_leaves_other_sessions_untouched(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        cookies = await _login_cookies(test_session, teacher)
        other = (await seed_sessions(test_session, teacher.id, 1))[0]

        other_id = other.id
        other_hash = other.refresh_token_hash

        await _refresh(test_session, redis_client, cookies)

        sessions = await get_sessions(test_session, teacher.id)
        untouched = next(s for s in sessions if s.id == other_id)

        assert untouched.refresh_token_hash == other_hash

    async def test_rotated_cookies_can_be_used_again(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        _, rotated = await _rotate(test_session, redis_client, teacher)

        result, _ = await _refresh(test_session, redis_client, rotated)

        assert result.access_token


class TestInvalidToken:
    @pytest.mark.parametrize("token", ["not-a-jwt", ""])
    async def test_garbage_token_rejected(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
        token,
    ):
        cookies = await _login_cookies(test_session, teacher)

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(
                test_session, redis_client, {**cookies, "refresh_token": token}
            )

    async def test_deleted_session_rejected(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        cookies = await _login_cookies(test_session, teacher)
        current = await _session_for(test_session, teacher, cookies)
        await test_session.delete(current)
        await test_session.flush()

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(test_session, redis_client, cookies)

    @pytest.mark.parametrize(
        "field",
        [
            "refresh_token_hash",
            "refresh_token_family_hash",
            "refresh_token_expires_at",
        ],
    )
    async def test_incomplete_session_rejected(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
        field,
    ):
        cookies = await _login_cookies(test_session, teacher)
        current = await _session_for(test_session, teacher, cookies)

        setattr(current, field, None)

        await test_session.flush()

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(test_session, redis_client, cookies)

    async def test_expired_session_rejected_without_revocation(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        cookies = await _login_cookies(test_session, teacher)
        current = await _session_for(test_session, teacher, cookies)

        current.refresh_token_expires_at = datetime.now(UTC) - timedelta(minutes=1)

        await test_session.flush()

        session_id = current.id

        with pytest.raises(exceptions.ExpiredRefreshTokenError):
            await _refresh(test_session, redis_client, cookies)

        assert not await _is_revoked(test_session, session_id)

    async def test_tampered_hash_revokes_session(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        cookies = await _login_cookies(test_session, teacher)
        current = await _session_for(test_session, teacher, cookies)

        current.refresh_token_hash = "tampered-hash"

        await test_session.flush()

        session_id = current.id
        version_before = current.access_token_version

        key = await _seed_version_key(redis_client, session_id)

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(test_session, redis_client, cookies)

        current = await _session_for(test_session, teacher, cookies)

        assert await _is_revoked(test_session, session_id)
        assert current.access_token_version == version_before + 1
        assert await redis_client.exists(key) == 0

    async def test_wrong_family_revokes_session(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        cookies = await _login_cookies(test_session, teacher)
        current = await _session_for(test_session, teacher, cookies)

        session_id = current.id
        version_before = current.access_token_version

        key = await _seed_version_key(redis_client, session_id)

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(
                test_session,
                redis_client,
                {**cookies, "refresh_token_family": "wrong-family"},
            )

        current = await _session_for(test_session, teacher, cookies)

        assert await _is_revoked(test_session, session_id)
        assert current.access_token_version == version_before + 1
        assert await redis_client.exists(key) == 0

    async def test_rejected_refresh_sets_no_cookies(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        cookies = await _login_cookies(test_session, teacher)
        response = Response()

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(
                test_session,
                redis_client,
                {**cookies, "refresh_token_family": "wrong-family"},
                response=response,
            )

        assert response.headers.getlist("set-cookie") == []


class TestReplay:
    async def test_old_token_after_rotation_revokes_session(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        original, _ = await _rotate(test_session, redis_client, teacher)
        current = await _session_for(test_session, teacher, original)

        session_id = current.id
        version_before = current.access_token_version

        key = await _seed_version_key(redis_client, session_id)

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(test_session, redis_client, original)

        current = await _session_for(test_session, teacher, original)

        assert await _is_revoked(test_session, session_id)
        assert current.access_token_version == version_before + 1
        assert await redis_client.exists(key) == 0

    async def test_rotated_token_is_dead_after_replay(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        original, rotated = await _rotate(test_session, redis_client, teacher)

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(test_session, redis_client, original)

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(test_session, redis_client, rotated)


class TestAccountStatus:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (UserStatus.PENDING_ACTIVATION, exceptions.AccountNotActivatedError),
            (UserStatus.DEACTIVATED, exceptions.AccountInactiveError),
            (UserStatus.GRADUATED, exceptions.AccountGraduatedError),
            (UserStatus.EXPELLED, exceptions.AccountExpelledError),
            (UserStatus.WITHDRAWN, exceptions.AccountWithdrawnError),
        ],
    )
    async def test_non_active_account_rejected(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
        status,
        expected,
    ):
        cookies = await _login_cookies(test_session, teacher)
        current = await _session_for(test_session, teacher, cookies)

        hash_before = current.refresh_token_hash
        teacher.status = status

        await test_session.flush()

        with pytest.raises(expected):
            await _refresh(test_session, redis_client, cookies)

        current = await _session_for(test_session, teacher, cookies)

        assert current.refresh_token_hash == hash_before

    async def test_pending_deletion_within_grace_can_refresh(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        cookies = await _login_cookies(test_session, teacher)

        teacher.status = UserStatus.PENDING_DELETION
        teacher.deletion_scheduled_for = datetime.now(UTC) + timedelta(days=5)

        await test_session.flush()

        result, _ = await _refresh(test_session, redis_client, cookies)

        assert result.access_token

    async def test_pending_deletion_with_expired_grace_rejected(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        cookies = await _login_cookies(test_session, teacher)

        teacher.status = UserStatus.PENDING_DELETION
        teacher.deletion_scheduled_for = datetime.now(UTC) - timedelta(minutes=1)

        await test_session.flush()

        with pytest.raises(exceptions.ExpiredDeletionGracePeriodError):
            await _refresh(test_session, redis_client, cookies)
