import uuid
from unittest.mock import AsyncMock, patch

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.services.system_admin import UserService
from src.users.utils.enums import AccountType, UserRole, UserStatus
from src.users.utils.exceptions import UserNotFoundError
from tests.factories import make_director, make_guardian, make_student, make_teacher

ENDPOINT = "/api/v1/admin/users/staff"


class TestNotFound:
    async def test_raises_when_public_id_does_not_exist(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        with pytest.raises(UserNotFoundError):
            await UserService.get_staff_by_public_id(
                test_session, redis_client, uuid.uuid4()
            )

    async def test_raises_for_student_public_id(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        student = await make_student(test_session)

        with pytest.raises(UserNotFoundError):
            await UserService.get_staff_by_public_id(
                test_session, redis_client, student.public_id
            )

    async def test_raises_for_guardian_public_id(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        guardian = await make_guardian(test_session)

        with pytest.raises(UserNotFoundError):
            await UserService.get_staff_by_public_id(
                test_session, redis_client, guardian.public_id
            )

    async def test_raises_for_system_admin_public_id(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ):
        with pytest.raises(UserNotFoundError):
            await UserService.get_staff_by_public_id(
                test_session, redis_client, system_admin.public_id
            )


class TestSuccess:
    async def test_returns_teacher(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        teacher = await make_teacher(test_session)

        result = await UserService.get_staff_by_public_id(
            test_session, redis_client, teacher.public_id
        )

        assert result.public_id == teacher.public_id
        assert result.role == UserRole.TEACHER
        assert result.account_type == AccountType.WORK

    async def test_returns_director(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        director = await make_director(test_session)

        result = await UserService.get_staff_by_public_id(
            test_session, redis_client, director.public_id
        )

        assert result.public_id == director.public_id
        assert result.role == UserRole.DIRECTOR

    async def test_response_shape(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        teacher = await make_teacher(test_session)

        result = await UserService.get_staff_by_public_id(
            test_session, redis_client, teacher.public_id
        )

        assert result.public_id == teacher.public_id
        assert result.username == teacher.username
        assert result.email == teacher.email
        assert result.account_type == AccountType.WORK
        assert result.status == UserStatus.ACTIVE
        assert result.deletion_scheduled_for is None
        assert result.created_at is not None
        assert result.updated_at is not None

    async def test_sets_cache_on_db_hit(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        teacher = await make_teacher(test_session)

        with patch(
            "src.users.services.system_admin.set_cache", new_callable=AsyncMock
        ) as mock_set_cache:
            await UserService.get_staff_by_public_id(
                test_session, redis_client, teacher.public_id
            )

            mock_set_cache.assert_called_once()


class TestCacheHit:
    async def test_returns_cached_data_without_hitting_db(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        teacher = await make_teacher(test_session)

        # Warm the cache
        await UserService.get_staff_by_public_id(
            test_session, redis_client, teacher.public_id
        )

        with patch(
            "src.users.services.system_admin.UserRepositoryBase.get_user_by_public_id",
            new_callable=AsyncMock,
        ) as mock_db:
            result = await UserService.get_staff_by_public_id(
                test_session, redis_client, teacher.public_id
            )

            mock_db.assert_not_called()

        assert result.public_id == teacher.public_id

    async def test_cache_miss_hits_db(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        teacher = await make_teacher(test_session)

        with (
            patch(
                "src.users.services.system_admin.get_cache",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.users.services.system_admin.UserRepositoryBase.get_user_by_public_id",
                wraps=lambda *a, **kw: UserService._original_get_user_by_public_id(
                    *a, **kw
                ),
            ) as mock_db,
        ):
            pass

        # Simpler: just assert DB is called when cache returns None
        with (
            patch(
                "src.users.services.system_admin.get_cache",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.users.services.system_admin.UserRepositoryBase.get_user_by_public_id",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_db,
            pytest.raises(UserNotFoundError),
        ):
            await UserService.get_staff_by_public_id(
                test_session, redis_client, teacher.public_id
            )

        mock_db.assert_called_once()
