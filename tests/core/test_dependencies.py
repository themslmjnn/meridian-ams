import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from fastapi import Response
from httpx import AsyncClient
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

import src.utils.exceptions as exceptions
from src.auth.schemas import CreateAccessToken, CreateRefreshToken
from src.core.config import get_settings
from src.core.dependencies import (
    STATUS_EXCEPTION_MAP,
    CurrentUser,
    _verify_status,
    get_session,
    require_roles,
)
from src.core.security import create_access_token, create_refresh_token
from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserSessionRepository
from src.users.utils.enums import AccountType, UserRole, UserStatus
from src.utils.cache_keys import SessionCacheKey
from tests.conftest import make_auth_header  # adjust if you import it elsewhere

settings = get_settings()

# Real routes used as probes. Adjust to your actual paths.
ME_URL = "/api/v1/users/me"  # any authenticated user
ADMIN_URL = "/api/v1/admin/users/staff"  # System Admin only
DIRECTOR_URL = "/api/v1/director/users/staff"  # Director only


def assert_error(response: Response, exc_cls) -> None:
    assert response.status_code == exc_cls.status_code
    assert response.json()["error_code"] == exc_cls.error_code


async def forged_header(
    test_session: AsyncSession, user_credentials: UserCredentials, **overrides
) -> dict[str, str]:
    """Like make_auth_header, but any token field can be overridden."""

    user_session = await UserSessionRepository.get_by_credentials_id(
        test_session, user_credentials.id
    )
    fields = {
        "public_id": user_credentials.public_id,
        "role": user_credentials.role,
        "account_type": user_credentials.account_type,
        "session_id": user_session.id,
        "access_token_version": user_session.access_token_version,
    }

    fields.update(overrides)

    return {
        "Authorization": f"Bearer {create_access_token(CreateAccessToken(**fields))}"
    }


def raw_header(*, exp_delta: timedelta = timedelta(minutes=5), **overrides) -> dict:
    """Sign arbitrary claims with the real secret, for malformed-claim cases."""

    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid.uuid4()),
        "role": "teacher",
        "account_type": "work",
        "session_id": 1,
        "atv": 1,
        "type": "access",
        "iat": now,
        "exp": now + exp_delta,
    }

    claims.update(overrides)

    token = jwt.encode(
        claims,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM,
    )

    return {"Authorization": f"Bearer {token}"}


async def cache_key_for(
    test_session: AsyncSession, user_credentials: UserCredentials
) -> str:
    user_session = await UserSessionRepository.get_by_credentials_id(
        test_session, user_credentials.id
    )

    return SessionCacheKey.access_token_version_key(user_session.id)


class TestTokenValidation:
    async def test_missing_header_returns_standard_401_body(
        self, integration_client: AsyncClient
    ):
        response = await integration_client.get(ME_URL)

        assert response.status_code == 401
        assert set(response.json().keys()) == {"error_code", "detail"}
        assert response.json()["detail"] == "Not authenticated"

    async def test_garbage_token_rejected(self, integration_client: AsyncClient):
        response = await integration_client.get(
            ME_URL, headers={"Authorization": "Bearer not-a-jwt"}
        )

        assert_error(response, exceptions.InvalidAccessTokenError)

    async def test_expired_token_rejected(self, integration_client: AsyncClient):
        response = await integration_client.get(
            ME_URL, headers=raw_header(exp_delta=timedelta(minutes=-1))
        )

        assert_error(response, exceptions.ExpiredAccessTokenError)

    async def test_wrong_signature_rejected(self, integration_client: AsyncClient):
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "type": "access",
                "iat": now,
                "exp": now + timedelta(minutes=5),
                "session_id": 1,
                "atv": 1,
            },
            "x" * 64,
            algorithm="HS256",
        )

        response = await integration_client.get(
            ME_URL, headers={"Authorization": f"Bearer {token}"}
        )

        assert_error(response, exceptions.InvalidAccessTokenError)

    async def test_refresh_token_not_accepted_as_access_token(
        self, integration_client: AsyncClient, teacher: UserCredentials
    ):
        token, _ = create_refresh_token(
            CreateRefreshToken(public_id=teacher.public_id, session_id=1)
        )

        response = await integration_client.get(
            ME_URL, headers={"Authorization": f"Bearer {token}"}
        )

        assert_error(response, exceptions.InvalidAccessTokenError)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"sub": "not-a-uuid"},
            {"role": "wizard"},
            {"account_type": "alien"},
            {"session_id": "abc"},
            {"atv": "abc"},
        ],
    )
    async def test_malformed_claim_values_return_401_not_500(
        self, integration_client: AsyncClient, overrides
    ):
        response = await integration_client.get(ME_URL, headers=raw_header(**overrides))

        assert_error(response, exceptions.InvalidAccessTokenError)


class TestCacheMissPath:
    async def test_valid_token_returns_user_and_populates_cache(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        headers = await make_auth_header(test_session, teacher)

        response = await integration_client.get(ME_URL, headers=headers)
        user_session = await UserSessionRepository.get_by_credentials_id(
            test_session, teacher.id
        )
        key = SessionCacheKey.access_token_version_key(user_session.id)

        assert response.status_code == 200
        assert await redis_client.get(key) == SessionCacheKey.pack_atv_cache(
            user_session.access_token_version, teacher.id
        )

    async def test_cache_ttl_is_capped(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        headers = await make_auth_header(test_session, teacher)

        await integration_client.get(ME_URL, headers=headers)
        ttl = await redis_client.ttl(await cache_key_for(test_session, teacher))

        assert 0 < ttl <= settings.ACCESS_TOKEN_EXPIRES_MINUTES * 60

    async def test_unknown_session_rejected(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        headers = await forged_header(test_session, teacher, session_id=999_999_999)

        response = await integration_client.get(ME_URL, headers=headers)

        assert_error(response, exceptions.InvalidAccessTokenError)
        assert response.json()["detail"] == "Session not found or has been revoked"

    async def test_public_id_mismatch_rejected(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        headers = await forged_header(test_session, teacher, public_id=uuid.uuid4())

        response = await integration_client.get(ME_URL, headers=headers)

        assert_error(response, exceptions.InvalidAccessTokenError)

    async def test_stale_atv_rejected(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        user_session = await UserSessionRepository.get_by_credentials_id(
            test_session, teacher.id
        )
        headers = await forged_header(
            test_session,
            teacher,
            access_token_version=user_session.access_token_version + 1,
        )

        response = await integration_client.get(ME_URL, headers=headers)

        assert_error(response, exceptions.InvalidAccessTokenError)

    async def test_session_belonging_to_another_user_rejected(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
        system_admin: UserCredentials,
    ):
        admin_session = await UserSessionRepository.get_by_credentials_id(
            test_session, system_admin.id
        )
        headers = await forged_header(
            test_session,
            teacher,
            session_id=admin_session.id,
            access_token_version=admin_session.access_token_version,
        )

        response = await integration_client.get(ME_URL, headers=headers)

        assert_error(response, exceptions.InvalidAccessTokenError)


class TestCacheHitPath:
    async def test_hit_skips_database(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        redis_client: Redis,
        teacher: UserCredentials,
        mocker,
    ):
        user_session = await UserSessionRepository.get_by_credentials_id(
            test_session, teacher.id
        )

        await redis_client.set(
            SessionCacheKey.access_token_version_key(user_session.id),
            SessionCacheKey.pack_atv_cache(
                user_session.access_token_version, teacher.id
            ),
        )

        headers = await make_auth_header(test_session, teacher)
        get_by_id = mocker.patch(
            "src.core.dependencies.UserSessionRepository.get_by_id",
            new_callable=AsyncMock,
        )

        response = await integration_client.get(ME_URL, headers=headers)

        assert response.status_code == 200
        get_by_id.assert_not_called()

    async def test_hit_with_mismatched_atv_rejected(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        user_session = await UserSessionRepository.get_by_credentials_id(
            test_session, teacher.id
        )

        await redis_client.set(
            SessionCacheKey.access_token_version_key(user_session.id),
            SessionCacheKey.pack_atv_cache(
                user_session.access_token_version + 1, teacher.id
            ),
        )

        headers = await make_auth_header(test_session, teacher)

        response = await integration_client.get(ME_URL, headers=headers)

        assert_error(response, exceptions.InvalidAccessTokenError)

    async def test_deleted_key_forces_database_recheck(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        redis_client: Redis,
        teacher: UserCredentials,
    ):
        headers = await make_auth_header(test_session, teacher)
        key = await cache_key_for(test_session, teacher)

        assert (
            await integration_client.get(ME_URL, headers=headers)
        ).status_code == 200
        assert await redis_client.exists(key) == 1

        # What logout / deactivation do: invalidate the key, and the DB decides.
        await redis_client.delete(key)
        teacher.status = UserStatus.DEACTIVATED
        await test_session.flush()

        response = await integration_client.get(ME_URL, headers=headers)

        assert_error(response, STATUS_EXCEPTION_MAP[UserStatus.DEACTIVATED])

    @pytest.mark.parametrize("malformed", ["garbage", "1", "a:b", ":", "1:"])
    async def test_malformed_cache_value_falls_back_to_db_and_is_overwritten(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        redis_client: Redis,
        teacher: UserCredentials,
        malformed,
    ):
        key = await cache_key_for(test_session, teacher)
        await redis_client.set(key, malformed)
        headers = await make_auth_header(test_session, teacher)

        response = await integration_client.get(ME_URL, headers=headers)
        user_session = await UserSessionRepository.get_by_credentials_id(
            test_session, teacher.id
        )

        assert response.status_code == 200
        assert await redis_client.get(key) == SessionCacheKey.pack_atv_cache(
            user_session.access_token_version, teacher.id
        )


class TestAccountStatus:
    async def test_active_account_allowed(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        teacher.status = UserStatus.ACTIVE
        await test_session.flush()

        response = await integration_client.get(
            ME_URL, headers=await make_auth_header(test_session, teacher)
        )

        assert response.status_code == 200

    @pytest.mark.parametrize(("status", "exc_cls"), list(STATUS_EXCEPTION_MAP.items()))
    async def test_each_blocked_status_returns_its_error(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        redis_client: Redis,
        teacher: UserCredentials,
        status,
        exc_cls,
    ):
        teacher.status = status
        teacher.deletion_scheduled_for = None
        await test_session.flush()

        response = await integration_client.get(
            ME_URL, headers=await make_auth_header(test_session, teacher)
        )

        assert_error(response, exc_cls)
        # A rejected account must never be cached as valid.
        key = await cache_key_for(test_session, teacher)
        assert await redis_client.exists(key) == 0

    async def test_pending_deletion_inside_grace_period_allowed(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        teacher.status = UserStatus.PENDING_DELETION
        teacher.deletion_scheduled_for = datetime.now(UTC) + timedelta(days=5)
        await test_session.flush()

        response = await integration_client.get(
            ME_URL, headers=await make_auth_header(test_session, teacher)
        )

        assert response.status_code == 200

    async def test_pending_deletion_after_grace_period_rejected(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        teacher.status = UserStatus.PENDING_DELETION
        teacher.deletion_scheduled_for = datetime.now(UTC) - timedelta(seconds=1)
        await test_session.flush()

        response = await integration_client.get(
            ME_URL, headers=await make_auth_header(test_session, teacher)
        )

        assert_error(response, STATUS_EXCEPTION_MAP[UserStatus.PENDING_DELETION])


class TestVerifyStatusUnit:
    def test_unknown_status_falls_back_to_access_denied(self):
        credentials = SimpleNamespace(status="mystery", deletion_scheduled_for=None)

        with pytest.raises(exceptions.AccessDeniedError):
            _verify_status(credentials)

    def test_pending_deletion_without_schedule_is_rejected(self):
        credentials = SimpleNamespace(
            status=UserStatus.PENDING_DELETION, deletion_scheduled_for=None
        )

        with pytest.raises(STATUS_EXCEPTION_MAP[UserStatus.PENDING_DELETION]):
            _verify_status(credentials)


class TestRoleGuards:
    async def test_system_admin_allowed_on_admin_route(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ):
        headers = await make_auth_header(test_session, system_admin)
        response = await integration_client.get(ADMIN_URL, headers=headers)

        assert response.status_code == 200

    async def test_teacher_gets_403_on_admin_route(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        headers = await make_auth_header(test_session, teacher)

        response = await integration_client.get(ADMIN_URL, headers=headers)

        assert_error(response, exceptions.AccessDeniedError)

    async def test_director_gets_403_on_admin_route(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        director: UserCredentials,
    ):
        headers = await make_auth_header(test_session, director)

        response = await integration_client.get(ADMIN_URL, headers=headers)

        assert_error(response, exceptions.AccessDeniedError)

    async def test_student_gets_403_on_admin_route(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        student: UserCredentials,
    ):
        headers = await make_auth_header(test_session, student)

        response = await integration_client.get(ADMIN_URL, headers=headers)

        assert_error(response, exceptions.AccessDeniedError)

    async def test_guardian_gets_403_on_admin_route(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        guardian: UserCredentials,
    ):
        headers = await make_auth_header(test_session, guardian)

        response = await integration_client.get(ADMIN_URL, headers=headers)

        assert_error(response, exceptions.AccessDeniedError)

    async def test_unauthenticated_request_is_401_not_403(
        self, integration_client: AsyncClient
    ):
        response = await integration_client.get(ADMIN_URL)

        assert response.status_code == 401

    def test_guard_accepts_any_of_several_roles(self):
        guard = require_roles(UserRole.TEACHER, UserRole.DIRECTOR)

        for role in (UserRole.TEACHER, UserRole.DIRECTOR):
            user = CurrentUser(1, uuid.uuid4(), role, AccountType.WORK, 1)

            assert guard(user) is user

    def test_guard_rejects_role_outside_the_set(self):
        guard = require_roles(UserRole.TEACHER, UserRole.DIRECTOR)
        user = CurrentUser(1, uuid.uuid4(), UserRole.SYSTEM_ADMIN, AccountType.WORK, 1)

        with pytest.raises(exceptions.AccessDeniedError):
            guard(user)


class TestRedisFailures:
    async def test_cache_read_failure_returns_503_not_a_bypass(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
        mocker,
    ):
        headers = await make_auth_header(test_session, teacher)
        mocker.patch(
            "src.core.dependencies.get_cache_critical",
            AsyncMock(side_effect=RedisError("AUTH failed: wrong password")),
        )

        response = await integration_client.get(ME_URL, headers=headers)

        assert response.status_code == 503
        assert response.json()["error_code"] == "SERVICE_UNAVAILABLE"
        assert "wrong password" not in response.text

    async def test_cache_write_failure_returns_503(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
        mocker,
    ):
        headers = await make_auth_header(test_session, teacher)
        mocker.patch(
            "src.core.dependencies.set_cache_critical",
            AsyncMock(side_effect=RedisError("write failed")),
        )

        response = await integration_client.get(ME_URL, headers=headers)

        assert response.status_code == 503


class TestGetSession:
    @staticmethod
    def _patch_factory(mocker) -> AsyncMock:
        session = AsyncMock()
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=session)
        context.__aexit__ = AsyncMock(return_value=False)
        mocker.patch("src.core.dependencies.session_factory", return_value=context)

        return session

    async def test_rolls_back_and_reraises_on_error(self, mocker):
        session = self._patch_factory(mocker)
        generator = get_session()

        assert await generator.__anext__() is session

        error = RuntimeError("boom")
        with pytest.raises(RuntimeError, match="boom"):
            await generator.athrow(error)

        session.rollback.assert_awaited_once()

    async def test_no_rollback_on_clean_exit(self, mocker):
        session = self._patch_factory(mocker)
        generator = get_session()

        await generator.__anext__()
        with pytest.raises(StopAsyncIteration):
            await generator.__anext__()

        session.rollback.assert_not_called()
