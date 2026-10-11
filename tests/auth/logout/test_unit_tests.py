from types import SimpleNamespace

from fastapi import Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.service import AuthService
from src.core.dependencies import CurrentUser
from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserSessionRepository
from src.utils.cache_keys import SessionCacheKey
from tests.auth.conftest import get_sessions, seed_sessions

REFRESH_PATH = "/api/v1/auth/refresh-token"


def _cookie_headers(response: Response):
    return {
        header.split("=", 1)[0]: header.lower()
        for header in response.headers.getlist("set-cookie")
    }


def _current_user(credentials, user_session):
    return CurrentUser(
        credentials_id=credentials.id,
        public_id=credentials.public_id,
        role=credentials.role,
        account_type=credentials.account_type,
        session_id=user_session.id,
    )


async def _logout(session: AsyncSession, redis: Redis, credentials, user_session):
    response = Response()

    await AuthService.logout(
        response, session, redis, _current_user(credentials, user_session)
    )

    return response


async def _seed_version_key(redis: Redis, session_id: int):
    key = SessionCacheKey.access_token_version_key(session_id)
    await redis.set(key, "1")

    return key


class TestSessionRemoval:
    async def test_deletes_current_session(
        self, test_session: AsyncSession, redis_client: Redis, teacher: UserCredentials
    ):
        current = (await get_sessions(test_session, teacher.id))[0]
        current_id = current.id

        await _logout(test_session, redis_client, teacher, current)

        assert await UserSessionRepository.get_by_id(test_session, current_id) is None

    async def test_keeps_other_sessions(
        self, test_session: AsyncSession, redis_client: Redis, teacher: UserCredentials
    ):
        current = (await get_sessions(test_session, teacher.id))[0]
        others = await seed_sessions(test_session, teacher.id, 2)

        other_ids = {s.id for s in others}
        current_id = current.id

        await _logout(test_session, redis_client, teacher, current)

        remaining = {s.id for s in await get_sessions(test_session, teacher.id)}

        assert current_id not in remaining
        assert remaining == other_ids

    async def test_already_deleted_session_is_a_noop(
        self, test_session: AsyncSession, redis_client: Redis, teacher: UserCredentials
    ):
        current = (await get_sessions(test_session, teacher.id))[0]
        key = await _seed_version_key(redis_client, current.id)

        await test_session.delete(current)
        await test_session.flush()

        response = await _logout(test_session, redis_client, teacher, current)

        assert await redis_client.exists(key) == 0
        assert set(_cookie_headers(response)) == {
            "refresh_token",
            "refresh_token_family",
        }


class TestCacheInvalidation:
    async def test_deletes_access_token_version_key(
        self, test_session: AsyncSession, redis_client: Redis, teacher: UserCredentials
    ):
        current = (await get_sessions(test_session, teacher.id))[0]
        key = await _seed_version_key(redis_client, current.id)

        await _logout(test_session, redis_client, teacher, current)

        assert await redis_client.exists(key) == 0

    async def test_leaves_other_sessions_keys(
        self, test_session: AsyncSession, redis_client: Redis, teacher: UserCredentials
    ):
        current = (await get_sessions(test_session, teacher.id))[0]
        other = (await seed_sessions(test_session, teacher.id, 1))[0]
        await _seed_version_key(redis_client, current.id)
        other_key = await _seed_version_key(redis_client, other.id)

        await _logout(test_session, redis_client, teacher, current)

        assert await redis_client.exists(other_key) == 1


class TestCookies:
    async def test_clears_refresh_cookies(
        self, test_session: AsyncSession, redis_client: Redis, teacher: UserCredentials
    ):
        current = (await get_sessions(test_session, teacher.id))[0]

        response = await _logout(test_session, redis_client, teacher, current)

        cookies = _cookie_headers(response)

        assert set(cookies) == {"refresh_token", "refresh_token_family"}
        for header in cookies.values():
            assert "max-age=0" in header
            assert f"path={REFRESH_PATH}" in header

    async def test_does_not_clear_device_id_cookie(
        self, test_session: AsyncSession, redis_client: Redis, teacher: UserCredentials
    ):
        current = (await get_sessions(test_session, teacher.id))[0]

        response = await _logout(test_session, redis_client, teacher, current)

        assert "device_id" not in _cookie_headers(response)
