from unittest.mock import AsyncMock, patch

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.services.shared import UserServiceSelf
from src.users.utils.exceptions import UserNotFoundError
from tests.factories import (
    make_director,
    make_guardian,
    make_student,
    make_system_admin,
    make_teacher,
)

ENDPOINT = "/api/v1/users/me"


class TestNotFound:
    async def test_raises_for_student_public_id(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        student = await make_student(test_session)
        current_user = _make_current_user(student)

        with pytest.raises(UserNotFoundError):
            await UserServiceSelf.get_my_profile(
                test_session, redis_client, current_user
            )


class TestSuccess:
    async def test_returns_teacher(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        teacher = await make_teacher(test_session)
        current_user = _make_current_user(teacher)

        result = await UserServiceSelf.get_my_profile(
            test_session, redis_client, current_user
        )

        assert result.public_id == teacher.public_id

    async def test_returns_system_admin(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        system_admin = await make_system_admin(test_session)
        current_user = _make_current_user(system_admin)

        result = await UserServiceSelf.get_my_profile(
            test_session, redis_client, current_user
        )

        assert result.public_id == system_admin.public_id

    async def test_returns_director(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        director = await make_director(test_session)
        current_user = _make_current_user(director)
        result = await UserServiceSelf.get_my_profile(
            test_session, redis_client, current_user
        )

        assert result.public_id == director.public_id

    async def test_returns_guardian(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        guardian = await make_guardian(test_session)
        current_user = _make_current_user(guardian)

        result = await UserServiceSelf.get_my_profile(
            test_session, redis_client, current_user
        )

        assert result.public_id == guardian.public_id

    async def test_response_shape(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        teacher = await make_teacher(test_session)
        current_user = _make_current_user(teacher)

        result = await UserServiceSelf.get_my_profile(
            test_session, redis_client, current_user
        )

        assert result.public_id == teacher.public_id
        assert result.username == teacher.username
        assert result.firstname is not None
        assert result.lastname is not None
        assert result.email == teacher.email
        assert result.phone_number is not None
        assert result.created_at is not None

    async def test_sets_cache_on_db_hit(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        teacher = await make_teacher(test_session)
        current_user = _make_current_user(teacher)

        with patch(
            "src.users.services.shared.set_cache", new_callable=AsyncMock
        ) as mock_set_cache:
            await UserServiceSelf.get_my_profile(
                test_session, redis_client, current_user
            )

            mock_set_cache.assert_called_once()


class TestCacheHit:
    async def test_returns_cached_data_without_hitting_db(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        teacher = await make_teacher(test_session)
        current_user = _make_current_user(teacher)

        # Warm the cache
        await UserServiceSelf.get_my_profile(test_session, redis_client, current_user)

        with patch(
            "src.users.services.shared.UserRepositoryBase.get_user_by_public_id",
            new_callable=AsyncMock,
        ) as mock_db:
            result = await UserServiceSelf.get_my_profile(
                test_session, redis_client, current_user
            )

            mock_db.assert_not_called()

        assert result.public_id == teacher.public_id

    async def test_cache_miss_hits_db(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        teacher = await make_teacher(test_session)
        current_user = _make_current_user(teacher)

        with (
            patch(
                "src.users.services.shared.get_cache",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.users.services.shared.UserRepositoryBase.get_user_by_public_id",
                wraps=lambda *a, **kw: (
                    UserServiceSelf.get_my_profile._original_get_user_by_public_id(
                        *a, **kw
                    )
                ),
            ) as mock_db,
        ):
            pass

        # Simpler: just assert DB is called when cache returns None
        with (
            patch(
                "src.users.services.shared.get_cache",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.users.services.shared.UserRepositoryBase.get_user_by_public_id",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_db,
            pytest.raises(UserNotFoundError),
        ):
            await UserServiceSelf.get_my_profile(
                test_session, redis_client, current_user
            )

        mock_db.assert_called_once()


def _make_current_user(credentials: UserCredentials):
    """
    Build a minimal CurrentUser-like object from a UserCredentials instance.
    Avoids going through login just to get a current_user context for service calls.
    """
    from types import SimpleNamespace

    return SimpleNamespace(
        credentials_id=credentials.id,
        public_id=credentials.public_id,
        role=credentials.role,
        account_type=credentials.account_type,
    )
