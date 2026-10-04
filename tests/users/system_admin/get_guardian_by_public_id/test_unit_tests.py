import uuid
from unittest.mock import AsyncMock, patch

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.services.system_admin import UserService
from src.users.utils.enums import AccountType, UserRole, UserStatus
from src.users.utils.exceptions import UserNotFoundError
from tests.factories import make_guardian, make_student, make_teacher

ENDPOINT = "/api/v1/admin/users/guardians"


class TestNotFound:
    async def test_raises_when_public_id_does_not_exist(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        with pytest.raises(UserNotFoundError):
            await UserService.get_guardian_by_public_id(
                test_session, redis_client, uuid.uuid4()
            )

    async def test_raises_for_teacher_public_id(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        teacher = await make_teacher(test_session)

        with pytest.raises(UserNotFoundError):
            await UserService.get_guardian_by_public_id(
                test_session, redis_client, teacher.public_id
            )

    async def test_raises_for_student_public_id(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        student = await make_student(test_session)

        with pytest.raises(UserNotFoundError):
            await UserService.get_guardian_by_public_id(
                test_session, redis_client, student.public_id
            )

    async def test_raises_for_system_admin_public_id(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
        system_admin: UserCredentials,
    ):
        with pytest.raises(UserNotFoundError):
            await UserService.get_guardian_by_public_id(
                test_session, redis_client, system_admin.public_id
            )


class TestSuccess:
    async def test_returns_guardian(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        guardian = await make_guardian(test_session)

        result = await UserService.get_guardian_by_public_id(
            test_session, redis_client, guardian.public_id
        )

        assert result.public_id == guardian.public_id
        assert result.role == UserRole.GUARDIAN
        assert result.account_type == AccountType.PERSONAL

    async def test_response_shape(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        guardian = await make_guardian(test_session)

        result = await UserService.get_guardian_by_public_id(
            test_session, redis_client, guardian.public_id
        )

        assert result.public_id == guardian.public_id
        assert result.username == guardian.username
        assert result.email == guardian.email
        assert result.account_type == AccountType.PERSONAL
        assert result.status == UserStatus.ACTIVE
        assert result.deletion_scheduled_for is None
        assert result.created_at is not None
        assert result.updated_at is not None

    async def test_sets_cache_on_db_hit(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        guardian = await make_guardian(test_session)

        with patch(
            "src.users.services.system_admin.set_cache", new_callable=AsyncMock
        ) as mock_set_cache:
            await UserService.get_guardian_by_public_id(
                test_session, redis_client, guardian.public_id
            )

            mock_set_cache.assert_called_once()


class TestCacheHit:
    async def test_returns_cached_data_without_hitting_db(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        guardian = await make_guardian(test_session)

        await UserService.get_guardian_by_public_id(
            test_session, redis_client, guardian.public_id
        )

        with patch(
            "src.users.services.system_admin.UserRepositoryBase.get_user_by_public_id",
            new_callable=AsyncMock,
        ) as mock_db:
            result = await UserService.get_guardian_by_public_id(
                test_session, redis_client, guardian.public_id
            )

            mock_db.assert_not_called()

        assert result.public_id == guardian.public_id

    async def test_cache_miss_hits_db(
        self,
        test_session: AsyncSession,
        redis_client: Redis,
    ):
        guardian = await make_guardian(test_session)

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
            await UserService.get_guardian_by_public_id(
                test_session, redis_client, guardian.public_id
            )

        mock_db.assert_called_once()
