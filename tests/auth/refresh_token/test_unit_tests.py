from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import Response
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.service import AuthService
from src.core.config import get_settings
from src.users.models.credentials import UserCredentials
from src.users.models.session import UserSession
from src.users.utils.enums import UserStatus
from src.utils import exceptions
from src.utils.cache_keys import SessionCacheKey
from tests.auth.conftest import (
    cookie_values,
    get_sessions,
    login_cookies,
    session_for_cookies,
)

settings = get_settings()


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


async def _is_revoked(session: AsyncSession, session_id: int) -> bool:
    query = (
        select(UserSession)
        .where(UserSession.id == session_id)
        .execution_options(populate_existing=True)
    )

    result = await session.execute(query)

    row = result.scalar_one_or_none()

    return row is None or row.refresh_token_hash is None


async def _seed_version_key(redis: Redis, session_id: int) -> str:
    key = SessionCacheKey.access_token_version_key(session_id)
    await redis.set(key, "1")

    return key


async def _rotate(session: AsyncSession, redis: Redis, user: UserCredentials):
    original = await login_cookies(session, user)
    _, response = await _refresh(session, redis, original)
    rotated = cookie_values(response.headers.getlist("set-cookie"))

    assert rotated["refresh_token"] != original["refresh_token"]
    assert rotated["refresh_token_family"] == original["refresh_token_family"]

    return original, rotated


class TestSuccessfulRotation:
    async def test_returns_bearer_token_with_expected_claims(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        login_user,
    ):
        cookies = await login_cookies(test_session, login_user)
        current = await session_for_cookies(test_session, login_user, cookies)

        result, _ = await _refresh(test_session, redis_client, cookies)

        claims = jwt.decode(result.access_token, options={"verify_signature": False})

        assert result.token_type == "bearer"
        assert claims["sub"] == str(login_user.public_id)
        assert claims["session_id"] == current.id

    async def test_rotates_session_state(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        login_user,
    ):
        cookies = await login_cookies(test_session, login_user)
        current = await session_for_cookies(test_session, login_user, cookies)
        old_refresh_token_hash = current.refresh_token_hash
        old_refresh_token_family_hash = current.refresh_token_family_hash

        await _refresh(test_session, redis_client, cookies)

        current = await session_for_cookies(test_session, login_user, cookies)
        expected_expiry = datetime.now(UTC) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRES_DAYS
        )

        assert current.refresh_token_hash != old_refresh_token_hash
        assert current.refresh_token_family_hash == old_refresh_token_family_hash
        assert current.last_active_at is not None
        assert (
            abs((current.refresh_token_expires_at - expected_expiry).total_seconds())
            < 5
        )

    async def test_sets_rotated_token_and_keeps_family_cookie(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        login_user,
    ):
        cookies = await login_cookies(test_session, login_user)

        _, response = await _refresh(test_session, redis_client, cookies)

        rotated = cookie_values(response.headers.getlist("set-cookie"))

        assert set(rotated) == {"refresh_token", "refresh_token_family"}
        assert rotated["refresh_token"] != cookies["refresh_token"]
        assert rotated["refresh_token_family"] == cookies["refresh_token_family"]

    async def test_leaves_other_sessions_untouched(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        login_user,
    ):
        cookies = await login_cookies(test_session, login_user)
        current = await session_for_cookies(test_session, login_user, cookies)
        before = {
            s.id: s.refresh_token_hash
            for s in await get_sessions(test_session, login_user.id)
            if s.id != current.id
        }

        await _refresh(test_session, redis_client, cookies)

        after = {
            s.id: s.refresh_token_hash
            for s in await get_sessions(test_session, login_user.id)
            if s.id != current.id
        }

        assert before
        assert after == before

    async def test_rotated_cookies_can_be_used_again(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        login_user,
    ):
        _, rotated = await _rotate(test_session, redis_client, login_user)

        result, _ = await _refresh(test_session, redis_client, rotated)

        assert result.access_token


class TestInvalidToken:
    @pytest.mark.parametrize("token", ["not-a-jwt", ""])
    async def test_garbage_token_rejected(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        login_user,
        token,
    ):
        cookies = await login_cookies(test_session, login_user)

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(
                test_session, redis_client, {**cookies, "refresh_token": token}
            )

    async def test_deleted_session_rejected(
        self, test_session: AsyncSession, redis_client: Redis, login_user
    ):
        cookies = await login_cookies(test_session, login_user)
        current = await session_for_cookies(test_session, login_user, cookies)
        await test_session.delete(current)
        await test_session.flush()

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(test_session, redis_client, cookies)

    @pytest.mark.parametrize(
        "field",
        ["refresh_token_hash", "refresh_token_family_hash", "refresh_token_expires_at"],
    )
    async def test_incomplete_session_rejected(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        login_user,
        field,
    ):
        cookies = await login_cookies(test_session, login_user)
        current = await session_for_cookies(test_session, login_user, cookies)
        setattr(current, field, None)
        await test_session.flush()

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(test_session, redis_client, cookies)

    async def test_expired_session_rejected_without_revocation(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        login_user,
    ):
        cookies = await login_cookies(test_session, login_user)
        current = await session_for_cookies(test_session, login_user, cookies)
        current.refresh_token_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await test_session.flush()
        session_id = current.id

        with pytest.raises(exceptions.ExpiredRefreshTokenError):
            await _refresh(test_session, redis_client, cookies)

        assert not await _is_revoked(test_session, session_id)

    async def test_unknown_token_revokes_session(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        login_user,
    ):
        cookies = await login_cookies(test_session, login_user)
        current = await session_for_cookies(test_session, login_user, cookies)
        current.refresh_token_hash = "tampered-hash"
        await test_session.flush()
        session_id = current.id
        version_before = current.access_token_version
        key = await _seed_version_key(redis_client, session_id)

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(test_session, redis_client, cookies)

        current = await session_for_cookies(test_session, login_user, cookies)

        assert await _is_revoked(test_session, session_id)
        assert current.access_token_version == version_before + 1
        assert await redis_client.exists(key) == 0

    async def test_wrong_family_revokes_session(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        login_user,
    ):
        cookies = await login_cookies(test_session, login_user)
        current = await session_for_cookies(test_session, login_user, cookies)
        session_id = current.id
        version_before = current.access_token_version
        key = await _seed_version_key(redis_client, session_id)

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(
                test_session,
                redis_client,
                {**cookies, "refresh_token_family": "wrong-family"},
            )

        current = await session_for_cookies(test_session, login_user, cookies)

        assert await _is_revoked(test_session, session_id)
        assert current.access_token_version == version_before + 1
        assert await redis_client.exists(key) == 0


class TestReplay:
    async def test_old_token_after_rotation_revokes_session(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        login_user,
    ):
        original, _ = await _rotate(test_session, redis_client, login_user)
        current = await session_for_cookies(test_session, login_user, original)
        session_id = current.id
        version_before = current.access_token_version
        key = await _seed_version_key(redis_client, session_id)

        with pytest.raises(exceptions.InvalidRefreshTokenError):
            await _refresh(test_session, redis_client, original)

        current = await session_for_cookies(test_session, login_user, original)

        assert await _is_revoked(test_session, session_id)
        assert current.access_token_version == version_before + 1
        assert await redis_client.exists(key) == 0

    async def test_rotated_token_is_dead_after_replay(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        login_user,
    ):
        original, rotated = await _rotate(test_session, redis_client, login_user)

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
        login_user,
        status,
        expected,
    ):
        cookies = await login_cookies(test_session, login_user)
        current = await session_for_cookies(test_session, login_user, cookies)
        hash_before = current.refresh_token_hash
        login_user.status = status
        await test_session.flush()

        with pytest.raises(expected):
            await _refresh(test_session, redis_client, cookies)

        current = await session_for_cookies(test_session, login_user, cookies)
        assert current.refresh_token_hash == hash_before

    async def test_pending_deletion_within_grace_can_refresh(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        login_user,
    ):
        cookies = await login_cookies(test_session, login_user)
        login_user.status = UserStatus.PENDING_DELETION
        login_user.deletion_scheduled_for = datetime.now(UTC) + timedelta(days=5)
        await test_session.flush()

        result, _ = await _refresh(test_session, redis_client, cookies)

        assert result.access_token

    async def test_pending_deletion_with_expired_grace_rejected(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        login_user,
    ):
        cookies = await login_cookies(test_session, login_user)
        login_user.status = UserStatus.PENDING_DELETION
        login_user.deletion_scheduled_for = datetime.now(UTC) - timedelta(minutes=1)
        await test_session.flush()

        with pytest.raises(exceptions.ExpiredDeletionGracePeriodError):
            await _refresh(test_session, redis_client, cookies)
